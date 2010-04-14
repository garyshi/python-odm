#!/usr/bin/python
import os
import ldap
import ldap.schema.subentry

def split_dn(dnstr):
	'''returns a tuple of rdn and superior-dn'''
	i = dnstr.find(',')
	return (dnstr[:i],dnstr[i+1:])

def parent_dn(dnstr):
	return split_dn(dnstr)[1]

# TODO: support date/time types, need to implement time zone
class LdapSyntaxTypeMapper:
	mappers = []

	class AbstractMapper:
		oid = None
		def ldap_to_python(self, value): pass
		def python_to_ldap(self, value): pass

	class DummyMapper(AbstractMapper):
		def ldap_to_python(self, value): return value
		def python_to_ldap(self, value): return value

	class BooleanMapper(AbstractMapper):
		oid = '1.3.6.1.4.1.1466.115.121.1.7'
		def ldap_to_python(self, value):
			return value == 'TRUE'
		def python_to_ldap(self, value):
			return value and 'TRUE' or 'FALSE'
	mappers.append(BooleanMapper)

	class UnicodeMapper(AbstractMapper):
		oid = '1.3.6.1.4.1.1466.115.121.1.15'
		def ldap_to_python(self, value):
			return value.decode('utf-8')
		def python_to_ldap(self, value):
			return value.encode('utf-8')
	mappers.append(UnicodeMapper)

	class IA5StringMapper(AbstractMapper):
		oid = '1.3.6.1.4.1.1466.115.121.1.26'
		def ldap_to_python(self, value):
			return str(value)
		def python_to_ldap(self, value):
			return str(value)
	mappers.append(IA5StringMapper)

	class IntegerMapper(AbstractMapper):
		oid = '1.3.6.1.4.1.1466.115.121.1.27'
		def ldap_to_python(self, value):
			return int(value)
		def python_to_ldap(self, value):
			return str(value)
	mappers.append(IntegerMapper)

	class NumstrMapper(AbstractMapper):
		'''will raise ValueError on format error'''
		oid = '1.3.6.1.4.1.1466.115.121.1.36'
		def ldap_to_python(self, value):
			return str(int(value))
		def python_to_ldap(self, value):
			return str(int(value))
	mappers.append(NumstrMapper)

	class GentimeMapper(AbstractMapper):
		# TODO: finish this. X.208 says if the string ends in 'Z',
		#	it's UTC; if it ends just after the second value,
		#	it's local time; need to know more about time zone
		#	postfix, and need to implement python tzinfo class.
		oid = '1.3.6.1.4.1.1466.115.121.1.24'

	class UTCTimeMapper(AbstractMapper):
		# TODO: finish this. but seems no core attributes use this,
		#	except the deprecated lastModifiedTime (replaced
		#	by modifyTimestamp) in cosine.schema.
		oid = '1.3.6.1.4.1.1466.115.121.1.53'

	def __init__(self):
		self.mapper = {}
		for mapper in self.mappers:
			self.mapper[mapper.oid] = mapper()

	def get_mapper(self, oid):
		if oid in self.mapper:
			return self.mapper[oid]
		return None

class LdapSchema:
	SubSchema = ldap.schema.subentry.SubSchema
	ObjectClass = ldap.schema.subentry.ObjectClass
	AttributeType = ldap.schema.subentry.AttributeType

	def __init__(self, schema):
		self.schema = schema
		self.mapper = LdapSyntaxTypeMapper()

	def from_server(cls, server):
		attrlist = ['subschemaSubentry']
		res = server.search_s('', ldap.SCOPE_BASE, attrlist=attrlist)
		dn = res[0][1]['subschemaSubentry'][0]
		attrlist = ['attributeTypes', 'objectClasses']
		res = server.search_s(dn, ldap.SCOPE_BASE, attrlist=attrlist)
		schema = cls.SubSchema(res[0][1])
		return cls(schema)

	from_server = classmethod(from_server)

	def get_attribute_type_syntax(self, nameoroid):
		return self.schema.get_inheritedattr(self.AttributeType,
			nameoroid, 'syntax')

	def get_attribute_type_mapper(self, nameoroid):
		syntax = self.get_attribute_type_syntax(nameoroid)
		return self.mapper.get_mapper(syntax)

	def get_object_class_attrs(self, nameoroid):
		suplist = [nameoroid]
		must_attrs,may_attrs = [],[]
		while suplist:
			nameoroid = suplist.pop(0)
			#print 'nameoroid:', nameoroid
			obj = self.schema.get_obj(self.ObjectClass, nameoroid)
			must_attrs.extend(obj.must)
			may_attrs.extend(obj.may)
			if hasattr(obj, 'sup') and obj.sup:
				if isinstance(obj.sup, tuple):
					suplist.extend(obj.sup)
				else:
					suplist.append(obj.sup)
		return must_attrs,may_attrs

class LdapObjectAttributeDefinition:
	def __init__(self, name, must, multi):
		self.name = name
		self.must = must
		self.multi = multi

	def schemarize(self, schema):
		self.syntax = schema.get_attribute_type_syntax(self.name)
		self.mapper = schema.mapper.get_mapper(self.syntax)

class LdapObjectDefinition:
	def __init__(self, oclist, attrlist):
		'''LdapObjectDefinition

		oclist: objectclass list for this LdapObject
		attrlist: attributes for this LdapObject, is a list of
			attribute names (case-sensitive), names are
			followed by repetion marker ?/*/+, or no marker
			if it's exactly single value.
			dn is implied, do not specify.
		'''
		self.oclist = oclist
		self.attrlist = []
		for attrdef in attrlist:
			rep = attrdef[-1]
			if   rep == '?':
				args = (attrdef[:-1], False, False)
			elif rep == '*':
				args = (attrdef[:-1], False, True)
			elif rep == '+':
				args = (attrdef[:-1], True, True)
			else:
				args = (attrdef, True, False)
			self.attrlist.append(LdapObjectAttributeDefinition(*args))

	def schemarize(self, schema):
		for attr in self.attrlist:
			attr.schemarize(schema)
		#map(lambda x: x.schemarize(schema), self.attrlist)


class LdapMapper:
	def __init__(self, server, schema=None):
		self.server = server
		self.schema = schema
		self.objdefs = {}

	# not very sure about this, but it works...
	def new_object(self, ldapobjcls, *args, **kwargs):
		objdef = self.objdefs[ldapobjcls]
		obj = super(ldapobjcls, ldapobjcls).__new__(ldapobjcls, *args, **kwargs)
		for attr in objdef.attrlist:
			if attr.multi:
				setattr(obj, attr.name, [])
			else:
				setattr(obj, attr.name, None)
		return obj

	def register(self, ldapobjcls, ldapobjdef):
		'''register an O-D mapper'''
		if self.schema: ldapobjdef.schemarize(self.schema)
		ldapobjcls.__new__ = staticmethod(self.new_object)
		self.objdefs[ldapobjcls] = ldapobjdef

	def unregister(self, ldapobjcls):
		'''unregister an O-D mapper by object class type'''
		del self.objdefs[ldapobjcls]

	def map_ldap_to_python(self, attrdef, values):
		if not self.schema: return values
		if not attrdef.mapper: return values
		mapper = attrdef.mapper
		return [mapper.ldap_to_python(v) for v in values]

	def map_python_to_ldap(self, attrdef, values):
		if not self.schema: return values
		if not attrdef.mapper: return values
		mapper = attrdef.mapper
		return [mapper.python_to_ldap(v) for v in values]

	def load(self, ldapobjcls, dn):
		'''load an ldap entry specified by dn into an object.

		if the entry does not exist, raise ldap.NO_SUCH_OBJECT exception.
		'''
		res = self.server.search_s(dn, ldap.SCOPE_BASE, '(objectclass=*)')[0]
		return self.build(ldapobjcls, res[0], res[1])

	def load_parent(self, ldapobjcls, obj):
		return self.load(ldapobjcls, parent_dn(obj.dn))

	def search(self, ldapobjcls, base, scope, filter=None):
		'''search for instances of ldapobjcls, and return mapped objs

		if no entries are found, return empty list. (raise no exceptions)
		'''

		objects = []
		if not filter: filter = '(objectclass=*)'
		for res in self.server.search_s(base, scope, filter):
			objects.append(self.build(ldapobjcls, res[0], res[1]))
		return objects

	def build(self, ldapobjcls, dn, attrs):
		'''build LdapObject of ldapobjcls with dn/attrs'''

		objdef = self.objdefs[ldapobjcls]
		obj = ldapobjcls.__new__(ldapobjcls)
		setattr(obj, 'dn', dn)
		for attrdef in objdef.attrlist:
			try:
				value = attrs[attrdef.name]
				value = self.map_ldap_to_python(attrdef, value)
				if not attrdef.multi: value = value[0]
				setattr(obj, attrdef.name, value)
			except KeyError:
				if attrdef.must: raise
		return obj

	def add(self, obj):
		'''add the obj into the ldap server'''

		objdef = self.objdefs[obj.__class__]
		oplist = [('objectClass', objdef.oclist)]
		for attrdef in objdef.attrlist:
			attr_name = attrdef.name
			if attr_name.lower() == 'objectclass': continue
			value = getattr(obj, attr_name, None)
			if value is not None: # FIXME: should this be "value is not None" or "not value"?
				if not attrdef.multi: value = [value]
				value = self.map_python_to_ldap(attrdef, value)
				oplist.append((attr_name, value))
		self.server.add_s(obj.dn, oplist)

	def modify(self, obj):
		'''modify the obj on the ldap server, the dn and the attribute of rdn can't be changed'''

		# load the object by obj.dn, so it can't be changed.
		# will raise ldap.NO_SUCH_OBJECT if the object doesn't exist.
		attrs = self.server.search_s(obj.dn, ldap.SCOPE_BASE, '(objectclass=*)')[0][1]

		oplist = []
		objdef = self.objdefs[obj.__class__]
		for attrdef in objdef.attrlist:
			attr_name = attrdef.name
			value = getattr(obj, attr_name, None)
			if attr_name.lower() == 'objectclass':
				oc1 = list(objdef.oclist)
				oc2 = list(value)
				oc1.sort()
				oc2.sort()
				if oc1 != oc2:
					oplist.append((ldap.MOD_REPLACE, attr_name, oc1))
				continue
			if value is not None:
				if not attrdef.multi: value = [value]
				value = self.map_python_to_ldap(attrdef, value)
				if attr_name in attrs:
					oplist.append((ldap.MOD_REPLACE, attr_name, value))
				else:
					oplist.append((ldap.MOD_ADD, attr_name, value))
			elif attr_name in attrs:
				oplist.append((ldap.MOD_DELETE, attr_name, None))

		self.server.modify_s(obj.dn, oplist)

	def delete(self, obj):
		'''delete the entry for the obj'''
		self.server.delete_s(obj.dn)

	def rename(self, obj, new_rdn, new_sdn=None, delold=True):
		old_rdn,old_sdn = split_dn(obj.dn)
		if new_sdn and old_sdn == new_sdn: new_sdn = None
		self.server.rename_s(obj.dn, new_rdn, new_sdn, delold)
		if not new_sdn: new_sdn = old_sdn
		# this will prevent rdn attribute to be multi-value
		# and we shall add type-casting here later
		old_attr = old_rdn.split('=')
		new_attr = new_rdn.split('=')
		if delold: delattr(obj, old_attr[0])
		setattr(obj, new_attr[0], new_attr[1])
		setattr(obj, 'dn', '%s,%s' % (new_rdn, new_sdn))

	def passwd(self, obj, old_passwd, new_passwd):
		self.server.passwd_s(obj.dn, old_passwd, new_passwd)
