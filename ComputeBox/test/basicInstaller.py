from fabric.api import run, put
import os

def install_prereqs():
    run('apt-get install python2.7 dialog nginx curl mc ssh mercurial python-gevent python-simplejson python-numpy byobu python-apt ipython python-pip python-imaging python-requests python-paramiko gcc g++ python-dev python-zmq msgpack-python python-mhash python-libvirt wget mercurial ssh python2.7 python-apt openssl ca-certificates -y')
    run('yes w | pip install urllib3 ujson blosc pycrypto pylzma')
    run('apt-get update')
    run('mkdir -p /home/ISO')
    run('wget -P /home/ISO/ http://files.incubaid.com/iaas/ubuntu-13.04-server-amd64.iso')
    WORKSPACE = os.environ.get('WORKSPACE')
    put(os.path.join(WORKSPACE, 'ComputeBox/test/libvirt_no_sparse.patch'), '/usr/share/pyshared/')
    put(os.path.join(WORKSPACE, 'ComputeBox/test/raring.patch'), '/tmp/')
    run('echo "\n[cloudscalers]\nmetadatafromtgz = 0\nqualitylevel = unstable\nmetadatadownload = \nmetadataupload = \nbitbucketaccount = incubaid\nbitbucketreponame = jp_cloudscalers\nblobstorremote = jpackages_remote\nblobstorlocal = jpackages_local" > /opt/jumpscale/cfg/jpackages/sources.cfg')
    put(os.path.join(WORKSPACE, 'config/*'), '~/.ssh/')
    run('jpackage_update')
    run('jpackage_install --package bootstrapper')