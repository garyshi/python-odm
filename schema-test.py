#!/usr/bin/python
import ldif

#f = open('/etc/openldap/schema/core.schema')
f = open('/etc/openldap/schema/core.ldif')
ldif_parser = ldif.LDIFRecordList(f)
ldif_parser.parse()
for record in ldif_parser.all_records:
	print record
