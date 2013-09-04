
[rootmodel:VMachine] @dbtype:osis
    """
    """
    prop:id int,,
    prop:name str,,name as given by customer
    prop:descr str,,
    prop:sizeId int,,id of size used by machine
    prop:imageId int,,id of image used to create machine
    prop:dedicatedCU bool,False,if true the compute capacity will be dedicated
    prop:disks list(int),,List of id of Disk objects
    prop:nics list(Nic),,List of id Nic objects (network interfaces) attached to this vmachine
    prop:realityUpdateEpoch int,,in epoch last time this object has been updated from reality
    prop:referenceId str,,name as used in hypervisor
    prop:accounts list(VMAccount),,list of machine accounts on the virtual machine
    prop:status str,,status of the vm (HALTED;INIT;RUNNING;TODELETE;SNAPSHOT;EXPORT)
    prop:hostName str,,hostname of the machine as specified by OS; is name in case no hostname is provided
    prop:cpus int,1,number of cpu assigned to the vm
    prop:boot bool,True,indicates if the virtual machine must automatically start upon boot of host machine
    prop:hypervisorType str,VMWARE,hypervisor running this vmachine (VMWARE;HYPERV;KVM)
    prop:resourceProviderId int,,ID of the resourceprovider
    prop:acl list(ACE),,access control list
    prop:cloudspaceId int,,id of space which holds this vmachine
    prop:networkGatewayIPv4 str,,IP address of the gateway for this vmachine

[model:VMAccount]
    """
    Machine account on the virtual machine
    """
    prop:login string,,login name of the machine account
    prop:password string,,password of the machine account

[rootmodel:Account] @dbtype:osis
    """
    Account owner of cloudspaces
    """
    prop:id int,,
    prop:name str,,Name of account
    prop:acl list(ACE),, access control list

[model:ACE]
    """
    Access control list
    """
    prop:userGroupId str,,unique identification of user or group
    prop:type str,,user or group (U or G)
    prop:right str,,right string now RWD  (depending type of object this action can be anything each type of action represented as 1 letter)

[rootmodel:Image] @dbtype:osis
    """
    """
    prop:id int,,
    prop:name str,,name of the image
    prop:description str,,extra description of the image
    prop:UNCPath str,,location of the image (uncpath like used in pylabs); includes the login/passwd info
    prop:size int,, size in MByte
    prop:type str,, dot separated list of independant terms known terms are: tar;gz;sso e.g. sso dump inn tar.gz format would be sso.tar.gz  (always in lcas)
    prop:referenceId str,,Name of the image on stack

[rootmodel:Stack] @dbtype:osis
    """
    """
    prop:id int,,
    prop:name str,,name as given by customer
    prop:descr str,,
    prop:login str,,login name if applicable
    prop:passwd str,,passwd if applicable
    prop:apikey str,,apikey if applicable
    prop:apiUrl str,,URL to communicate to the stack
    prop:type str,,Type of the stack, (OPENSTACK|CLOUDFRAMES|XEN SOURCE)
    prop:appId str,,application id if applicable
    prop:realityUpdateEpoch int,,in epoch last time this stack has been completely read out & our model updated
 

[rootmodel:Disk] @dbtype:osis
    """
    """
    prop:id int,,
    prop:name str,,name as given by customer
    prop:descr str,,
    prop:sizeMax int,,provisioned size of disk in MB
    prop:sizeUsed int,,used capacity of disk in MB
    prop:realityUpdateEpoch int,,in epoch last time this object has been updated from reality
    prop:referenceId str,,name as used in hypervisor
    prop:realityDeviceNumber int,, Number a device gets after connect
    prop:status str,,status of the vm (ACTIVE;INIT;IMAGE)
    prop:type str,,(RAW,ISCSI)
    prop:resourceProviderId int,,ID of the resourceprovider
    prop:acl dict(ACE),,access control list    
    prop:role str,,role of disk (BOOT; DATA; TEMP)
    prop:order int,,order of the disk (as will be shown in OS)
    prop:iqn str,,location of iscsi backend e.g. iqn.2009-11.com.aserver:b6d2aa75-d5ae-4e5a-a38a-12c64c787be6
    prop:diskPath str,, Holds the path of the disk
    prop:login str,,login of e.g. iqn connection
    prop:passwd str,,passwd of e.g. iqn connection
    prop:params str,,pylabs tags to define optional params
    prop:bootPartition int,,the partition to boot from if disk is a bootdisk
    prop:images list(int),,List of id of Image object

[rootmodel:Network] @dbtype:osis
    """
    """
    prop:id int,,
    prop:name str,,name as given by customer
    prop:descr str,,
    prop:stackId int,,IAAS stack ID
    prop:vlanId str,,ethernet vlan tag
    prop:subnet str,,subnet of the network
    prop:netmask str,,netmask of the network
    prop:nameservers list(str),,Nameservers
    prop:cloudspaceId int,,id of space which holds this network

[model:Nic] @dbtype:osis
    """
    """
    prop:realityUpdateEpoch int,,in epoch last time this object has been updated from reality
    prop:referenceId str,,name as used in hypervisor
    prop:networkId int,,id of Network object
    prop:status str,,status of the vm (ACTIVE;INIT;DOWN)
    prop:deviceName str,,name of the device as on device
    prop:macAddress str,,MAC address of the vnic
    prop:ipAddress str,,IP address of the vnic
    prop:params str,,pylabs tags to define optional params

[rootmodel:ResourceProvider] @dbtype:osis
    prop:id int,,
    prop:stackId int,,IAAS stack ID
    prop:cloudUnitType str,, (CU,VSU,SU,NU)
    prop:capacityAvailable int,, e.g. 10 CU available
    prop:referenceId str,,Id of the resourceprovider on the stack

[rootmodel:CloudSpace] @dbtype:osis
    """
    """
    prop:id int,,
    prop:name str,,name as given by customer
    prop:descr str,,
    prop:acl list(ACE),,access control list
    prop:accountId int,, Id of account this cloudspace belongs to
    prop:resourceProviderStacks list(int),,ordered list of stacks which provide resources; values are the id's of the stacks
    prop:resourceLimits dict(int),,key:$stackid_$cloudunittype value:int amount of max nr of units which can be used there
    prop:resourcesUsed dict(ResourceUtilization),,key is type of resource (CU;SU;VSU)

[model:ResourceUtilization]
    """
    """
    prop:diskID int,0,
    prop:machineID int,0,
    prop:type str,, (CU,SU,VSU)
    prop:history dict(ResourceUtilizationHistory),,key is epochhour

[model:ResourceUtilizationHistory]
    """
    """
    prop:resourceProviderId int,,id of provider of this capacity
    prop:epochHour int,,is unique int which represents an hour in history
    prop:amount int,,capacity used e.g. 10 CU at that specific hour

[rootmodel:Size] @dbtype:osis
    """
    Size is a combination of CU and Storage.
    It will map to a specific size on a cloud platform(if this is supported by the platform)
    When not supported, the integration code for the platform uses the disksize and CU.
    """
    prop:id int, 0,id of the size
    prop:name str,,Public name of the size
    prop:CU int,,Number of CU
    prop:disks int,,disk size in MB
    prop:referenceId str,,Reference to the specific size on the cloud platform(if used)