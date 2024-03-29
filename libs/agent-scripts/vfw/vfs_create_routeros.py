from JumpScale import j

descr = """
create and start a routeros image
"""

organization = "jumpscale"
author = "deboeckj@codescalers.com"
license = "bsd"
version = "1.0"
category = "deploy.routeros"
enable = True
async = True
queue = 'default'
docleanup = True


def cleanup(name, networkid):
    import libvirt
    from CloudscalerLibcloud.utils import libvirtutil
    con = libvirt.open()
    try:
        dom = con.lookupByName(name)
        if dom.isActive():
            dom.destroy()
        dom.undefine()
    except libvirt.libvirtError:
        pass

    try:
        libvirtutil.LibvirtUtil().cleanupNetwork(networkid)
    except:
        pass

    destination = '/var/lib/libvirt/images/routeros/'
    networkidHex = '%04x' % int(networkid)
    if j.system.fs.exists(j.system.fs.joinPaths(destination, networkidHex)):
        j.system.btrfs.subvolumeDelete(destination, networkidHex)


def createVM(xml):
    import libvirt
    con = libvirt.open()
    dom = con.defineXML(xml)
    dom.create()


def action(networkid, publicip, publicgwip, publiccidr, password, vlan):
    import pexpect
    import netaddr
    import jinja2
    import time
    import os

    hrd = j.atyourservice.get(name='vfwnode', instance='main').hrd
    netrange = hrd.get("instance.vfw.netrange.internal")
    defaultpasswd = hrd.get("instance.vfw.admin.passwd")
    username = hrd.get("instance.vfw.admin.login")
    newpassword = hrd.get("instance.vfw.admin.newpasswd")
    destinationfile = None

    data = {'nid': j.application.whoAmI.nid,
            'gid': j.application.whoAmI.gid,
            'username': username,
            'password': newpassword
            }

    jumpscript = j.clients.redisworker.getJumpscriptFromName('greenitglobe', 'create_external_network')
    bridgename = j.clients.redisworker.execJumpscript(jumpscript=jumpscript, vlan=vlan).result

    networkidHex = '%04x' % int(networkid)
    internalip = str(netaddr.IPAddress(netaddr.IPNetwork(netrange).first + int(networkid)))
    name = 'routeros_%s' % networkidHex

    j.clients.redisworker.execFunction(cleanup, _queue='hypervisor', name=name,
                                       networkid=networkid)
    print 'Testing network'
    if not j.system.net.tcpPortConnectionTest(internalip, 22, 1):
        print "OK no other router found."
    else:
        raise RuntimeError("IP conflict there is router with %s" % internalip)

    try:
        # setup network vxlan
        print 'Creating network'
        createnetwork = j.clients.redisworker.getJumpscriptFromName('greenitglobe', 'createnetwork')
        j.clients.redisworker.execJumpscript(jumpscript=createnetwork, _queue='hypervisor', networkid=networkid)
        templatepath = '/var/lib/libvirt/images/routeros/template/'
        destination = '/var/lib/libvirt/images/routeros/%s' % networkidHex
        print 'Creating image snapshot %s -> %s' % (templatepath, destination)
        if j.system.fs.exists(destination):
            raise RuntimeError("Path %s already exists" % destination)
        j.system.btrfs.snapshot(templatepath, destination)

        destinationfile = os.path.join(destination, 'routeros.qcow2')
        imagedir = j.system.fs.joinPaths(j.dirs.baseDir, 'apps/routeros/template/')
        xmltemplate = jinja2.Template(j.system.fs.fileGetContents(j.system.fs.joinPaths(imagedir, 'routeros-template.xml')))

        xmlsource = xmltemplate.render(networkid=networkidHex, destinationfile=destinationfile, publicbridge=bridgename)

        print 'Starting VM'
        try:
            j.clients.redisworker.execFunction(createVM, _queue='hypervisor', xml=xmlsource)
        except Exception, e:
            raise RuntimeError("Could not create VFW vm from template, network id:%s:%s\n%s" % (networkid, networkidHex, e))

        data['internalip'] = internalip

        try:
            run = pexpect.spawn("virsh console %s" % name, timeout=300)
            print "Waiting to attach to console"
            run.expect("Connected to domain", timeout=10)
            run.sendline()  # first enter to clear welcome message of kvm console
            print 'Waiting for Login'
            run.expect("Login:", timeout=120)
            run.sendline(username)
            run.expect("Password:", timeout=10)
            run.sendline(defaultpasswd)
            print 'waiting for prompt'
            run.expect("\] >", timeout=120)  # wait for primpt
            run.send("/ip addr add address=%s/22 interface=ether3\r\n" % internalip)
            print 'waiting for end of command'
            run.expect("\] >", timeout=10)  # wait for primpt
            run.send("/quit\r\n")
            run.expect("Login:", timeout=10)
            run.close()
        except Exception, e:
            raise RuntimeError("Could not set internal ip on VFW, network id:%s:%s\n%s" % (networkid, networkidHex, e))

        print "wait max 30 sec on tcp port 22 connection to '%s'" % internalip
        if j.system.net.waitConnectionTest(internalip, 80, timeout=30):
            print "Router is accessible, initial configuration probably ok."
        else:
            raise RuntimeError("Could not connect to router on %s" % internalip)

        ro = j.clients.routeros.get(internalip, username, defaultpasswd)
        ro.do("/system/identity/set", {"name": "%s/%s" % (networkid, networkidHex)})
        ro.executeScript('/file remove numbers=[/file find]')

        # create certificates
        certdir = j.system.fs.getTmpDirPath()
        j.tools.sslSigning.create_self_signed_ca_cert(certdir)
        j.tools.sslSigning.createSignedCert(certdir, 'server')

        ro.uploadFilesFromDir(certdir)
        vpnpassword = j.tools.hash.sha1(j.system.fs.joinPaths(certdir, 'ca.crt'))
        j.system.fs.removeDirTree(certdir)

        if "skins" not in ro.list("/"):
            ro.mkdir("/skins")
        ro.uploadFilesFromDir("skins", "/skins")

        pubip = "%s/%s" % (publicip, publiccidr)
        privateip = "192.168.103.1/24"
        ro.uploadExecuteScript("basicnetwork", vars={'$pubip': pubip, '$privateip': privateip})
        ro.uploadExecuteScript("route", vars={'$gw': publicgwip})
        ro.uploadExecuteScript("certificates")
        ro.uploadExecuteScript("ppp", vars={'$vpnpassword': vpnpassword})
        ro.uploadExecuteScript("systemscripts")
        ro.uploadExecuteScript("services")

        # skin default
        ro.uploadExecuteScript("customer", vars={'$password': password})

        # dirty cludge: rebooting ROS here, as ftp service doesn't propagate directories
        ro.executeScript('/system reboot')
        ro.close()

        # We're waiting for reboot
        start = time.time()
        timeout = 60
        while time.time() - start < timeout:
            try:
                ro = j.clients.routeros.get(internalip, username, defaultpasswd)
                ro.executeScript("/user group set [find name=customer] skin=customer")
                ro.close()
                break
            except Exception as e:
                print 'Failed to set skin will try again in 1sec', e
            time.sleep(1)
        else:
            raise RuntimeError("Failed to set customer skin")

        if not ro.arping(publicgwip, 'public'):
            raise RuntimeError("Could not ping to:%s for VFW %s" % (publicgwip, networkid))

        # now, set the pasword
        try:
            ro = j.clients.routeros.get(internalip, username, defaultpasswd)
            ro.executeScript('/user set %s password=%s' % (username, newpassword))
        except:
            pass

        ro.close()
        print 'Finished configuring VFW'

    except:
        if docleanup:
            j.clients.redisworker.execFunction(cleanup, _queue='hypervisor', name=name,
                                               networkid=networkid)
        raise

    return data


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('-n', '--networkid', type=int, required=True)
    parser.add_argument('-p', '--public-ip', dest='publicip', required=True)
    parser.add_argument('-pg', '--public-gw', dest='publicgw', required=True)
    parser.add_argument('-pc', '--public-cidr', dest='publiccidr', required=True, type=int)
    parser.add_argument('-v', '--vlan', dest='vlan', required=True, type=int)
    parser.add_argument('-pw', '--password', default='rooter')
    parser.add_argument('-c', '--cleanup', action='store_true', default=False, help='Cleanup in case of failure')
    options = parser.parse_args()
    docleanup = options.cleanup
    action(options.networkid, options.publicip, options.publicgw, options.publiccidr, options.password, options.vlan)
