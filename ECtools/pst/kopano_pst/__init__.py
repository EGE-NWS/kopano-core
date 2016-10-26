#!/usr/bin/python
import time
import pst
import kopano
from MAPI.Util import *
import MAPI.Time

class Service(kopano.Service):

    def import_props(self, parent, mapiobj): # XXX fully recurse
        props2 = []
        for k, v in parent.pc.props.items():
            propid, proptype, value = k, v.wPropType, v.value
            if proptype == PT_SYSTIME:
                value = MAPI.Time.unixtime(time.mktime(value.timetuple()))
            nameid = self.propid_nameid.get(propid)
            if nameid:
                propid = PROP_ID(mapiobj.GetIDsFromNames([MAPINAMEID(*nameid)], 0)[0])
            if propid == PR_ATTACH_DATA_OBJ >> 16 and len(value) == 4: # XXX why not 4
                subnode_nid = struct.unpack('I', value)[0]
                message = pst.Message(subnode_nid, self.ltp, self.nbd, parent)
                message2 = mapiobj.OpenProperty(PR_ATTACH_DATA_OBJ, IID_IMessage, 0, MAPI_CREATE | MAPI_MODIFY)
                subprops = []
                for l, w in message.pc.props.items():
                    value = w.value
                    if w.wPropType == PT_SYSTIME:
                        value = MAPI.Time.unixtime(time.mktime(value.timetuple()))
                    subprops.append(SPropValue(PROP_TAG(w.wPropType, l), value))
                message2.SetProps(subprops)
                message2.SaveChanges(KEEP_OPEN_READWRITE)
            else:
                props2.append(SPropValue(PROP_TAG(proptype, propid), value))
        mapiobj.SetProps(props2)
        mapiobj.SaveChanges(KEEP_OPEN_READWRITE)

    def import_attachments(self, message, message2):
        for attachment in message.subattachments:
            attachment = message.get_attachment(attachment)
            (id_, attachment2) = message2.mapiobj.CreateAttach(None, 0)
            self.import_props(attachment, attachment2)

    def import_recipients(self, message, message2):
        recipients = [] # XXX group etc entryid?, exchange user?
        for r in message.subrecipients:
            props = [
                SPropValue(PR_RECIPIENT_TYPE, r.RecipientType),
                SPropValue(PR_DISPLAY_NAME_W, r.DisplayName),
                SPropValue(PR_ADDRTYPE_W, r.AddressType),
            ]
            if r.EmailAddress:
                props.append(SPropValue(PR_EMAIL_ADDRESS_W, r.EmailAddress))
            if r.AddressType == 'ZARAFA' and r.ObjectType==6 and not '@' in r.EmailAddress: # XXX broken props?
                user = kopano.user(r.EmailAddress)
                props.append(SPropValue(PR_ENTRYID, user.userid.decode('hex')))
            recipients.append(props)
        message2.mapiobj.ModifyRecipients(0, recipients)
        message2.mapiobj.SaveChanges(KEEP_OPEN_READWRITE)

    def import_pst(self, pst, user): # XXX check embedded msgs
        for folder in pst.folder_generator():
            path = folder.path[1:]
            if self.options.folders and path not in self.options.folders:
                continue
            self.log.info("importing folder '%s'" % path)
            folder2 = user.folder(path, create=True)
            if folder.ContainerClass:
                folder2.container_class = folder.ContainerClass
            for message in pst.message_generator(folder):
                self.log.debug("importing message '%s'" % message.Subject)
                message2 = folder2.create_item()
                self.import_props(message, message2.mapiobj)
                self.import_attachments(message, message2)
                self.import_recipients(message, message2)

    def get_named_property_map(self, pst):
        propid_nameid = {}
        for nameid in pst.messaging.nameid_entries:
            propid_nameid[nameid.NPID] = (
                nameid.guid,
                MNID_STRING if nameid.N==1 else MNID_ID,
                nameid.name if nameid.N==1 else nameid.dwPropertyID
            )
        return propid_nameid

    def main(self):
        for arg in self.args:
            self.log.info("importing file '%s'" % arg)
            p = pst.PST(arg)
            self.nbd, self.ltp = p.nbd, p.ltp
            self.propid_nameid = self.get_named_property_map(p)
            for name in self.options.users:
                self.log.info("importing to user '%s'" % name)
                self.import_pst(p, kopano.user(name))

def main():
    parser = kopano.parser('cflskpUPu', usage='kopano-pst PATH -u NAME')

#    parser.add_option('', '--restore-root', dest='restore_root', help='restore under specific folder', metavar='PATH')
#    parser.add_option('', '--stats', dest='stats', action='store_true', help='list folders for PATH')
#    parser.add_option('', '--index', dest='index', action='store_true', help='list items for PATH')
#    parser.add_option('', '--recursive', dest='recursive', action='store_true', help='backup/restore folders recursively')
#    empty respective folders before import?

    options, args = parser.parse_args()
    options.service = False

    assert args, 'please specify path(s) to .pst file(s)'
    assert options.users, 'please specify user(s) to import to'

    Service('pst', options=options, args=args).start()

if __name__ == '__main__':
    main()
