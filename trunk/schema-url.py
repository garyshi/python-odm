#!/usr/bin/python
import sys

import ldap.schema.subentry

url = 'file:///home/garyshi/python/test/ldap/core4.ldif'
#url = 'file:///etc/openldap/schema/core.ldif'
#url = 'file:///etc/openldap/schema/core.schema'
dn,schema = ldap.schema.subentry.urlfetch(url)
#print schema.name2oid
#print schema.sed
print schema.get_syntax('cn')
print schema.get_syntax('street')
print schema.get_syntax('postalAddress')
print schema.get_syntax('registeredAddress')
obj = schema.get_obj(ldap.schema.subentry.AttributeType, 'registeredAddress')
print obj
print obj.equality
print schema.get_obj(ldap.schema.subentry.ObjectClass, 'person')
print schema.attribute_types('person', raise_keyerror=False)
