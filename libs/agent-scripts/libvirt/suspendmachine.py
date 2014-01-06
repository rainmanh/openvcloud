from JumpScale import j

descr = """
Libvirt script to suspend a virtual machine
"""

name = "suspendmachine"
category = "libvirt"
organization = "cloudscalers"
author = "hendrik@awingu.com"
license = "bsd"
version = "1.0"
roles = ["*"]


def action(machineid, xml=None):
    from CloudscalerLibcloud.utils.libvirtutil import LibvirtUtil
    connection = LibvirtUtil()
    return connection.suspend(machineid)

