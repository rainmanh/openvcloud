#!/usr/bin/env jspython
from JumpScale import j
from JumpScale.baselib import cmdutils


parser = cmdutils.ArgumentParser()
parser.add_argument('--cpunode', action='store_true', default=False)
parser.add_argument('--accounts', action='store_true', default=False)
parser.add_argument('--nose', action='store_true', default=False)
parser.add_argument('--destroyed', action='store_true', default=False)

opts = parser.parse_args()

ccl = j.clients.osis.getNamespace('cloudbroker')
scl = j.clients.osis.getNamespace('system')
lcl = j.clients.osis.getNamespace('libvirt')
pcl = j.clients.portal.getByInstance('main')

q = {}

if opts.destroyed:
    q = {'status': 'DESTROYED'}

if opts.cpunode or opts.accounts or opts.destroyed:
    ccl.vmachine.deleteSearch(q)
    ccl.disk.deleteSearch(q)
    ccl.cloudspace.deleteSearch(q)
    ccl.account.deleteSearch(q)
if opts.cpunode:
    ccl.stack.deleteSearch({})
    ccl.image.deleteSearch({})
    lcl.resourceprovider.deleteSearch({})
    lcl.image.deleteSearch({})
if opts.nose:
    for ac in ccl.account.search({'name': {'$regex': '[a-f0-9]{10}'}})[1:]:
        print '* Deleting %(name)s' % ac
        pcl.actors.cloudbroker.account.delete(ac['id'])
    scl.user.deleteSearch({'name': {'$regex': '[a-f0-9]{10}'}})

j.application.stop(0)
