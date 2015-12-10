## Release 1.2

## Release 1.1-rc1 - 2015-12-08

### Comments

### Improvement
    * [CELL-36] - Upgrade Amoeba to CentOS-7.1
    * [CELL-40] - Move quickstart-1 to amoeba
    * [CELL-45] - Public ELBs to monitor and administer Mesos and other components
    * [CELL-51] - Assign different instance types based on the role assigned to an instance
    * [CELL-60] - Add cell-os-base-1.1-SNAPSHOT bundle 
    * [CELL-61] - Change S3 access from keys to IAM role-based access
    * [CELL-62] - Node index defaults to 0, requires index to always be specified
    * [CELL-63] - Reduce unnecessary security groups membership
    * [CELL-71] - cell-cli - allocate a tty on ./cell cmd to allow sudo 
    * [CELL-72] - cf template - saasbase_installer should fetch specified version of embedded modules instead of latest
    * [CELL-75] - Incorrect CF link in README
    * [CELL-76] - CellOsVersionBundle default should be the same as current version (1.1)
    * [CELL-77] - Cell membrane
    * [CELL-79] - Cell stateful body
    * [CELL-82] - elastic cell-os HDFS support
    * [CELL-86] - Extract CF scaling group logic in reusable (nested) stack 
    * [CELL-89] - install cell-os-base JDK 
    * [CELL-91] - Open nucleus access to load balancers
    * [CELL-93] - pre / post zk-barrier modules 
    * [CELL-94] - Marathon LB should check /status instead of / 
    * [CELL-98] - Set instance timezone to UTC
    * [CELL-99] - Troposphere Port
    * [CELL-100] - Hadoop support
    * [CELL-101] - ./cell support for i2cssh
    * [CELL-102] - Drop raw json CF support
    * [CELL-104] - ./cell refactor to use functions
    * [CELL-105] - ./cell override variables from enviornment
    * [CELL-106] - ./cell get path to cell-os dir
    * [CELL-107] - introduce UserData base map that gets on all stacks 
    * [CELL-108] - Use SaasBase access keys only for puppet run
    * [CELL-109] - ./cell list shouldn't output nested stacks
    * [CELL-116] - ./cell i2cssh to role 
    * [CELL-117] - troposphere build support
    * [CELL-121] - Can't create cells with names larger than 7 characters 
    * [CELL-124] - Membrane IAM for read only s3 access
    * [CELL-125] - [RFC] - cell-os-base deployment packages / modules
    * [CELL-127] - Amoeba should use released artifacts instead of git repos
    * [CELL-131] - Add python requirements.txt to the cell-os project
    * [CELL-141] - Ability to configure instance root device size
    * [CELL-144] - Add Adobe Paris egress IP 
    * [CELL-146] - Amoeba: use Vagrant vm.provision instead of ssh to bootstrap
    * [CELL-65] - Pass the AWS region to cluster.yaml in the CF template 

### Bug
    * [CELL-64] - CellOS only works in us-west-2 due to Exhibitor
    * [CELL-69] - cell-cli list <cell> doesn't set output type
    * [CELL-70] - nucleus config doesn't install cfn-bootstrap
    * [CELL-74] - cell-cli doesn't delete s3 bucket
    * [CELL-90] - disable puppet-marathon JDK install
    * [CELL-96] - AWS_OPTIONS are not passed when describing instances
    * [CELL-103] - Minor issues with HDFS provisioning
    * [CELL-118] - CF launch stack should use released template 
    * [CELL-122] - DNS issues in AWS us-east-1
    * [CELL-128] - ./cell i2cssh to all the roles does not work
    * [CELL-129] - Cell nucleus nodes shouldn't run mesos-agent
    * [CELL-130] - Cell update does not work because of the --tags option

