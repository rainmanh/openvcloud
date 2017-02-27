from JumpScale import j
from CloudscalerLibcloud.utils import libvirtutil
from . import rules


class Network(object):
    def __init__(self):
        self.libvirtutil = libvirtutil.LibvirtUtil()

    def cleanup_flows(self, bridge, port, mac):
        cmd = rules.CLEANUPFLOWS_CMD.format(mac=mac, port=port, bridge=bridge)
        j.system.process.execute(cmd)

    def get_public_interface(self, domain):
        for nic in self.libvirtutil.get_domain_nics_info(domain):
            if nic['bridge'].startswith('pub') or nic['bridge'].startwith('ext'):
                return nic['name'], nic['mac'], nic['bridge']

    def get_gwmgmt_interface(self, domain):
        for nic in self.libvirtutil.get_domain_nics_info(domain):
            if nic['bridge'] == 'gw_mgmt':
                return nic['name'], nic['mac']

    def get_port(self, interface):
        portcmd = 'ovs-vsctl -f table -d bare --no-heading -- --columns=ofport list Interface {}'.format(interface)
        exitcode, port = j.system.process.execute(portcmd)
        return port.strip()

    def cleanup_public(self, domain):
        interface, mac, bridge = self.get_public_interface(domain)
        port = self.get_port(interface)
        self.cleanup_flows(bridge, port, mac)

    def protect_public(self, domain, ipaddress):
        interface, mac, bridge = self.get_public_interface(domain)
        port = self.get_port(interface)
        self.cleanup_flows(bridge, port)
        tmpfile = j.system.fs.getTmpFilePath()
        j.system.fs.writeFile(tmpfile, rules.PUBLICINPUT.format(port=port, mac=mac, publicipv4addr=ipaddress))
        j.system.process.execute("ovs-ofctl add-flows {bridge} {file}".format(file=tmpfile, bridge=bridge))

    def protect_gwmgmt(self, domain, ipaddress):
        interface, mac = self.get_gwmgmt_interface(domain)
        port = self.get_port(interface)
        tmpfile = j.system.fs.getTmpFilePath()
        j.system.fs.writeFile(tmpfile, rules.GWMGMTINPUT.format(port=port, mac=mac, ipaddress=ipaddress))
        j.system.process.execute("ovs-ofctl add-flows {bridge} {file}".format(file=tmpfile, bridge='gw_mgmt'))

    def cleanup_gwmgmt(self, domain):
        interface, mac = self.get_gwmgmt_interface(domain)
        port = self.get_port(interface)
        self.cleanup_flows('gw_mgmt', port, mac)
