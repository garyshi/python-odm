#!/usr/bin/python
import sys
import ldap
import odm

class VirtualDomain(object):
	pass

class VirtualAccount(object):
	def __init__(self, domain=None, cn=None):
		if domain:
			self.cn = cn
			self.dn = 'cn=%s,%s' % (cn, domain.dn)
			self.uid = '%s-%s' % (domain.cn, cn)
			self.gidNumber = domain.gidNumber
			self.homeDirectory = '/home/vmail/%s/%s' % (domain.cn, cn)


VD_oclist = ('posixGroup','domainRelatedObject')
VD_aclist = ('cn','gidNumber','associatedDomain*')
VD_objdef = odm.LdapObjectDefinition(VD_oclist, VD_aclist)
VA_oclist = ('person','posixAccount','inetOrgPerson','organizationalPerson')
VA_aclist = ('sn','givenName?','cn','uid','uidNumber','gidNumber','homeDirectory','userPassword?','displayName?','mail*')
VA_objdef = odm.LdapObjectDefinition(VA_oclist, VA_aclist)

base_dn = 'dc=my-domain,dc=com'
server = ldap.open('localhost')
server.simple_bind_s('cn=Manager,dc=my-domain,dc=com', 'secret')
schema = odm.LdapSchema.from_server(server)
mapper = odm.LdapMapper(server, schema)
mapper.register(VirtualDomain, VD_objdef)
mapper.register(VirtualAccount, VA_objdef)

filter = 'mail=test@vmail.winworld.cn'
va = mapper.search(VirtualAccount, base_dn, ldap.SCOPE_SUBTREE, filter)[0]
domain = mapper.load_parent(VirtualDomain, va)
print va
print 'dn:', va.dn
print 'cn:', va.cn
print 'sn:', va.sn
print 'uid:', va.uid
print 'uidNumber:', va.uidNumber, type(va.uidNumber)
print 'gidNumber:', va.gidNumber, type(va.gidNumber)
print 'homeDirectory:', va.homeDirectory
print 'mail:', va.mail
va.displayName = 'Test Account'
mapper.modify(va)

filter = 'cn=foobar'
result = mapper.search(VirtualAccount, domain.dn, ldap.SCOPE_SUBTREE, filter)
if len(result): mapper.delete(result[0])
#sys.exit(0)

va = VirtualAccount(domain, 'foobar')
print va.displayName
va.sn = 'Foo'
va.givenName = 'Bar'
va.displayName = 'Foo Bar'
va.uidNumber = str(5001)
va.mail = ['foobar@vmail.winworld.cn', 'foobar2k@vmail.winworld.cn']
mapper.add(va)

delattr(va, 'displayName')
mapper.modify(va)
