import os
import string

import awacs
import awacs.ec2
import awacs.aws
import awacs.sts
import awacs.s3
import awacs.sqs
import awacs.autoscaling
import awacs.cloudformation
import awacs.cloudfront
import awacs.cloudwatch
import awacs.dynamodb
import awacs.elasticloadbalancing
import awacs.iam

import troposphere.iam as iam
import troposphere.ec2 as ec2
import troposphere.elasticloadbalancing as elb
import troposphere.cloudformation as cfn
import troposphere.autoscaling as asn
from tropopause import *

from troposphere import Not, Ref, Equals, If, Tags

t = Template()

t.add_version("2010-09-09")

t.add_description("""\
cell-os-base - https://git.corp.adobe.com/metal-cell/cell-os""")
instance_type = t.add_parameter(Parameter(
    "InstanceType",
    ConstraintDescription="must be a valid, HVM-compatible EC2 instance type.",
    Type="String",
    Description="EC2 instance type",
    AllowedValues=[
        "t2.micro", "t2.small", "t2.medium", "t2.large",
        "m1.small", "m1.medium", "m1.large", "m1.xlarge",
        "m2.xlarge", "m2.2xlarge", "m2.4xlarge",
        "m3.medium", "m3.large", "m3.xlarge", "m3.2xlarge",
        "m4.large", "m4.xlarge", "m4.2xlarge", "m4.4xlarge", "m4.10xlarge",
        "c4.large", "c4.xlarge", "c4.2xlarge", "c4.4xlarge", "c4.8xlarge",
        "c3.large", "c3.xlarge", "c3.2xlarge", "c3.4xlarge", "c3.8xlarge",
        "r3.large", "r3.xlarge", "r3.2xlarge", "r3.4xlarge", "r3.8xlarge",
        "g2.2xlarge", "g2.8xlarge",
        "i2.xlarge", "i2.2xlarge", "i2.4xlarge", "i2.8xlarge",
        "d2.xlarge", "d2.2xlarge", "d2.4xlarge", "d2.8xlarge",
        "hs1.8xlarge",
        "hi1.4xlarge",
        "cc2.8xlarge"
    ],
))

cell_name = t.add_parameter(Parameter(
    "CellName",
    Type="String",
    Description="The name of this cell (e.g. cell-1). This will get prefixed with account id and region to get the full cell id.",
))

bucket_name = t.add_parameter(Parameter(
    "BucketName",
    Type="String",
    Description="Cell's S3 bucket name. Used for metadata and backups. Can be one per account as we prefix data with cell name inside",
))

Repository = t.add_parameter(Parameter(
    "Repository",
    Type="String",
    Description="Location of Cell-OS related artifacts",
))

cell_os_version_bundle = t.add_parameter(Parameter(
    "CellOsVersionBundle",
    Type="String",
    Description="cell-os bundle version",
))

key_name = t.add_parameter(Parameter(
    "KeyName",
    Type="AWS::EC2::KeyPair::KeyName",
    Description="Existing EC2 KeyPair to be associated with all cluster instances for SSH access. The default user is 'centos'",
))

group_size = t.add_parameter(Parameter(
    "GroupSize",
    Type="Number",
    Description="Number of nodes in the scaling group",
))


load_balancer_names = t.add_parameter(Parameter(
    "LoadBalancerNames",
    Type="CommaDelimitedList",
    Description="List of ELBs that ",
))

zookeeper_load_balancer = t.add_parameter(Parameter(
    "ZookeeperElb",
    Type="String",
    Description="ZK ELB Endpoint",
))

marathon_load_balancer = t.add_parameter(Parameter(
    "MarathonElb",
    Type="String",
    Description="Marathon ELB Endpoint",
))

mesos_load_balancer = t.add_parameter(Parameter(
    "MesosElb",
    Type="String",
    Description="Mesos ELB Endpoint",
))

gateway_load_balancer = t.add_parameter(Parameter(
    "GatewayElb",
    Type="String",
    Description="Gateway ELB Endpoint",
))

internal_gateway_load_balancer = t.add_parameter(Parameter(
    "InternalGatewayElb",
    Type="String",
    Description="Internal Gateway ELB Endpoint",
))

subnet = t.add_parameter(Parameter(
    "Subnet",
    Type="AWS::EC2::Subnet::Id",
    Description="Subnet",
))

tags = t.add_parameter(Parameter(
    "Tags",
    Type="CommaDelimitedList",
    Description="Comma separated list of tags",
))

image_id = t.add_parameter(Parameter(
    "ImageId",
    Type="AWS::EC2::Image::Id",
    Description="AMI ID",
))

security_groups = t.add_parameter(Parameter(
    "SecurityGroups",
    Type="List<AWS::EC2::SecurityGroup::Id>",
    Description="AMI ID",
))

iam_instance_profile = t.add_parameter(Parameter(
    "IamInstanceProfile",
    Default="",
    Type="String",
    Description="IAM Profile if any",
))

role = t.add_parameter(Parameter(
    "Role",
    Type="String",
    Description="The role of the autoscaling group (stateless-body, membrane, etc.)",
))

parent_stack_name = t.add_parameter(Parameter(
    "ParentStackName",
    Type="String",
    Description="",
))

wait_handle = t.add_parameter(Parameter(
    "WaitHandle",
    Type="String",
    Description="",
))

associate_public_ip_address = t.add_parameter(Parameter(
    "AssociatePublicIpAddress",
    Default="false",
    Type="String",
    Description="AMI ID",
    AllowedValues=["true", "false"],
))

cell_modules = t.add_parameter(Parameter(
    "CellModules",
    Type="String",
    Description="Comma separated list of modules",
))

saasbase_access_key_id = t.add_parameter(Parameter(
    "SaasBaseAccessKeyId",
    Type="String",
    Description="SaasBase S3 repo read-only AWS account Access Key ID (http://saasbase.corp.adobe.com/ops/operations/deployment.html)",
))

saasbase_secret_access_key = t.add_parameter(Parameter(
    "SaasBaseSecretAccessKey",
    Type="String",
    Description="SaasBase S3 repo read-only AWS account Secret Access Key (http://saasbase.corp.adobe.com/ops/operations/deployment.html)",
))

t.add_condition(
    "HasIamInstanceProfile", Not(Equals(Ref(iam_instance_profile), ""))
)

body = t.add_resource(asn.AutoScalingGroup(
    "Body",
    DesiredCapacity=Ref(group_size),
    Tags=asn.Tags(
        role=Ref(role),
        cell=Ref(cell_name),
    ),
    LaunchConfigurationName=Ref("BodyLaunchConfig"),
    MinSize="0",
    MaxSize="1000",
    VPCZoneIdentifier=[Ref(subnet)],
    LoadBalancerNames=Ref(load_balancer_names),
    TerminationPolicies=["NewestInstance", "ClosestToNextInstanceHour"]
))

ROOT_DEVICE_SIZE = 200
root_block_device_mapping = [
    ec2.BlockDeviceMapping(
        DeviceName='/dev/sda1',
        Ebs=ec2.EBSBlockDevice(
            DeleteOnTermination=True,
            VolumeType='gp2',
            VolumeSize=ROOT_DEVICE_SIZE
        )
    )
]

BodyLaunchConfig = t.add_resource(asn.LaunchConfiguration(
    "BodyLaunchConfig",
    Metadata=cfn.Init({
        "config": cfn.InitConfig(
            files=cfn.InitFiles({
                "/usr/local/bin/jq": cfn.InitFile(
                    source="https://github.com/stedolan/jq/releases/download/jq-1.5/jq-linux64",
                    owner="root",
                    group="root",
                    mode="000755"
                ),
                "/etc/profile.d/cellos.sh": cfn.InitFile(
                    content=make_content("""\
#!/bin/bash
export cell_backend="aws"
export cell_name="{{cell_name}}"
export full_cell_name="cell-os--{{cell_name}}"
export zk_elb="{{zk_elb}}"
export zk_base_url="{{zk_base_url}}"
export zk_cluster_list="{{zk_base_url}}/cluster/list"
export marathon_elb="{{marathon_elb}}"
export mesos_elb="{{mesos_elb}}"
export gateway_elb="{{gateway_elb}}"
export internal_gateway_elb="{{internal_gateway_elb}}"
export SAASBASE_ACCESS_KEY_ID="{{saasbase_access_key_id}}"
export SAASBASE_SECRET_ACCESS_KEY="{{saasbase_secret_access_key}}"
export repository="{{repository}}"
export cellos_version="{{cellos_version}}"
export cell_bucket_name="{{cell_bucket_name}}"
export cell_role="{{cell_role}}"
export cell_modules="{{cell_modules}}"

export machine_tags="{{machine_tags}}"
export instance_id=`wget -qO- http://169.254.169.254/latest/meta-data/instance-id`
export aws_stack_name="{{aws_stack_name}}"
export aws_parent_stack_name="{{aws_parent_stack_name}}"
export aws_region="{{aws_region}}"
export aws_access_key_id="{{aws_access_key_id}}"
export aws_secret_access_key="{{aws_secret_access_key}}"
export aws_wait_handle="{{aws_wait_handle}}"
"""),
                    owner="root",
                    group="root",
                    mode="000755",
                    context=cfn.InitFileContext({
                        "zk_base_url": Join("", ["http://", Ref("ZookeeperElb"), "/exhibitor/v1"]),
                        "zk_elb": Ref("ZookeeperElb"),
                        "marathon_elb": Ref("MarathonElb"),
                        "mesos_elb": Ref("MesosElb"),
                        "gateway_elb": Ref("GatewayElb"),
                        "internal_gateway_elb": Ref("InternalGatewayElb"),
                        "aws_stack_name": Ref("AWS::StackName"),
                        "aws_parent_stack_name": Ref("ParentStackName"),
                        "aws_region": Ref("AWS::Region"),
                        "saasbase_access_key_id": Ref("SaasBaseAccessKeyId"),
                        "saasbase_secret_access_key": Ref("SaasBaseSecretAccessKey"),
                        "repository": Ref("Repository"),
                        "cellos_version": Ref("CellOsVersionBundle"),
                        "cell_bucket_name": Ref("BucketName"),
                        "cell_name": Ref("CellName"),
                        "cell_role": Ref("Role"),
                        "cell_modules": Ref("CellModules"),
                        "machine_tags": Ref("Tags"),
                        "aws_wait_handle": Ref("WaitHandle"),
                    })
                ),
                "/usr/local/bin/aws_wait": cfn.InitFile(
                    content=make_content("""\
#!/bin/bash
[[ $# = 3 ]] || { echo "Internal error calling wait-for" ; exit 99 ; }
cmd=$1
pattern=$2
target=$3
loop=1
echo "Waiting for $cmd | jq \\"$pattern\\""
while [[ $loop -le 200 ]]; do
    STATE=$($cmd | jq "$pattern")
    if [[ "$STATE" == "$target" ]]; then
        exit 0
    fi
    sleep 5
    printf "."
    loop=$(( $loop + 1 ))
done
exit 1
"""),
                    owner="root",
                    group="root",
                    mode="000755"
                ),
                "/usr/local/bin/zk-list-nodes": cfn.InitFile(
                    content=make_content("""\
#!/bin/bash
source /etc/profile.d/cellos.sh
num_servers=${num_servers:-0}
code=$(curl -s -o /dev/null -w "%{http_code}" ${zk_cluster_list})
if (( code == 200 )); then
  # we have a 200, get the servers
  found=$(curl -H "Accept: application/json" ${zk_cluster_list} 2>/dev/null | jq ".servers | length")
  if (( $? == 0 )); then
    if (( $found < $num_servers )); then
      >&2 echo "not enough servers found ($found out of $num_servers)"
      exit 1
    fi
  else
    >&2 echo no servers found
    exit 1
  fi
else
  >&2 echo no servers found
  exit 1
fi

curl -H "Accept: application/json" ${zk_cluster_list} 2>/dev/null | jq -r '(.port | tostring) as $port | .servers | map(. + ":" + $port) | join(",")'
"""),
                    owner="root",
                    group="root",
                    mode="000755",
                ),
                "/usr/local/bin/zk-barrier": cfn.InitFile(
                    content=make_content("""\
#!/bin/bash
### Block until we have a ZK quorum
num_servers=3
while true; do
  code=$(curl -H "Accept: application/json" -s -o /dev/null -w "%{http_code}" "${zk_base_url}/cluster/status")
  if (( code == 200 )); then
    num_serving=$(curl -H "Accept: application/json" "${zk_base_url}/cluster/status" 2>/dev/null | jq '[.[] | select(.description == "serving")] | length')
    num_serving=${num_serving:-0}
    found=$(curl -H "Accept: application/json" ${zk_cluster_list} 2>/dev/null | jq ".servers | length")
    found=${found:-0}

    if (( $num_serving >= $num_servers && $found >= $num_servers )); then
      # check servers
      valid=()
      for hp in $(zk-list-nodes | sed 's/,/\\n/g'); do
        host=$(echo $hp | sed 's/:.*$//')
        exec 6<>/dev/tcp/$host/2181 && valid+=($host)
      done
      if (( ${#valid[@]}  >= $num_servers )); then
        break
      else
        echo -n "."
        sleep 1
      fi
    else
      echo -n "."
      sleep 1
    fi
  else
    echo -n "."
    sleep 1
  fi
done
"""),
                    owner="root",
                    group="root",
                    mode="000755"
                ),
                "/usr/local/bin/provision": cfn.InitFile(
                    content=make_content("""\
#!/bin/bash
# provision script
# provisioner puppet role1,role2,role3
source /etc/profile.d/cellos.sh

provision_with_retry() {
  local roles=${1?"usage provision_with_retry <roles> [retries]"}
  local module_name=${2:${roles}}
  local max_attempts=${3:-5}
  local attempt=0
  local status=-1
  until [[ $status == 0 ]]; do
    bash /usr/local/bin/saasbase_installer -v -d /opt/cell -m /opt/cell/cluster/puppet/modules run-puppet /opt/cell/cluster --roles $roles
    status=$?
    attempt=$(($attempt + 1))
    if [[ $attempt -gt $max_attempts ]]; then
      exit 1
    fi
    if [[ $status != 0 ]]; then
      echo "Retry ${1} provisioning step: exit code $status, attempt $attempt / $max_attempts"
      report_status "${module_name} retry"
    fi
  done
}


if [[ $1 == "puppet" ]]; then
    shift
    AWS_ACCESS_KEY_ID="${SAASBASE_ACCESS_KEY_ID}" AWS_SECRET_ACCESS_KEY="${SAASBASE_SECRET_ACCESS_KEY}" \
    provision_with_retry $@
fi
"""),
                    owner="root",
                    group="root",
                    mode="000755"
                ),
                "/usr/local/bin/detect-and-mount-disks": cfn.InitFile(
                    content=make_content("""\
#!/bin/bash
deviceslist=('/dev/xvdb' '/dev/xvdc' '/dev/xvdd' '/dev/xvde' '/dev/xvdf' '/dev/xvdg' '/dev/xvdh' '/dev/xvdi' '/dev/xvdj' '/dev/xvdk' '/dev/xvdl' '/dev/xvdm' '/dev/xvdn' '/dev/xvdo' '/dev/xvdp' '/dev/xvdq' '/dev/xvdr' '/dev/xvds' '/dev/xvdt' '/dev/xvdu' '/dev/xvdv' '/dev/xvdw' '/dev/xvdx' '/dev/xvdy' '/dev/xvdz')
for device in ${deviceslist[@]}; do
    if ([ -b $device ]) then
        actual_devices=( "${actual_devices[@]}" $device )
    fi
done

n=0
for device in "${actual_devices[@]}"; do
    n=`expr $n + 1`
    if [ ! -b ${device}1 ]; then
        echo "Creating partition on ${device}" >&2
        parted -s -a optimal $device mklabel gpt -- mkpart primary xfs 1 -1 >&2
        partprobe $device >&2 || true
        mkfs.xfs ${device}1 >&2 || true
    fi
    if mountpoint -q -- "/mnt/data_${n}"; then
        echo "/mnt/data_${n} is already mounted" >&2
    else
        echo "$1 is not a mountpoint" >&2
        mkdir -p -m 755 /mnt/data_${n} >&2
        mount ${device}1 /mnt/data_${n} >&2 || true
        echo "${device}1 /mnt/data_${n} xfs rw,relatime,attr2,inode64,noquota,nofail 0 0" >> /etc/fstab
    fi

    mkdir -p -m 755 /mnt/data_${n}/{hadoop_data,kafka_data}
    chown -R hadoop:hadoop /mnt/data_${n}/{hadoop_data,kafka_data}
done
echo $n
"""),
                    owner="root",
                    group="root",
                    mode="000755"
                ),
                "/usr/local/bin/get_ip": cfn.InitFile(
                    content=make_content("""\
#!/bin/sh
set -o nounset -o errexit
if [ -e /etc/environment ]
then
  set -o allexport
  source /etc/environment
  set +o allexport
fi

get_private_ip() {
    curl -fsSL http://169.254.169.254/latest/meta-data/local-ipv4
}

echo $(get_private_ip)
"""),
                    owner="root",
                    group="root",
                    mode="000755"
                ),
                "/usr/local/bin/report_status": cfn.InitFile(
                    content=make_content("""\
#!/bin/bash

source /etc/profile.d/cellos.sh
mkdir -p /opt/cell/status

message=$@
ts=$(date +"%s")
status_file=/opt/cell/status/${instance_id}.json

echo -e "${message} ${ts}" | tee -a $status_file

aws s3 cp $status_file s3://${cell_bucket_name}/${full_cell_name}/shared/status/${instance_id} \
    --metadata-directive REPLACE --cache-control max-age=0,public \
    --expires 2000-01-01T00:00:00Z &>/dev/null
"""),
                    owner="root",
                    group="root",
                    mode="000755"
                ),
                "/usr/local/bin/yaml2json": cfn.InitFile(
                    content=make_content("""\
#!/bin/bash
set -o pipefail

python -c 'import sys, yaml, json; json.dump(yaml.load(sys.stdin), sys.stdout, indent=4)' | cat "$@"
"""),
                    owner="root",
                    group="root",
                    mode="000755"
                ),
                "/usr/local/bin/machine_for_role": cfn.InitFile(
                    content=make_content("""\
#!/bin/bash
# This script returns either the ip or the host for a cell machine in a certain
# role
# Usage: machine_for_role <role> <index> <host|ip>
# - role: nucleus, stateful-body, stateless-body, membrane
# - index: starting from 1
# - host|ip
# FIXME: we assume describe instances always returns the instances in the ASG
#        order; this might not be the case (when instances break, for example)
source /etc/profile.d/cellos.sh
role=$1
index=$(( $2 - 1 ))
[[ "$3" == "ip" ]] && ret=0
[[ "$3" == "host" ]] && ret=1
machine=$(aws --region ${aws_region} ec2 describe-instances --query 'Reservations[*].Instances[*].[PrivateIpAddress, PrivateDnsName]' --filters Name=instance-state-code,Values=16 Name=tag:cell,Values=${cell_name} Name=tag:role,Values=${role} | jq -r ".[0][${index}][${ret}]")
echo $machine
"""),
                    owner="root",
                    group="root",
                    mode="000755"
                ),
            })
        )
    }),
    ImageId=Ref(image_id),
    KeyName=Ref(key_name),
    SecurityGroups=Ref(security_groups),
    BlockDeviceMappings=root_block_device_mapping + [
        ec2.BlockDeviceMapping(
            VirtualName='ephemeral%d' % i,
            DeviceName='/dev/sd%s' % chr(98 + i)
        ) for i in range(23)
    ],
    IamInstanceProfile=If("HasIamInstanceProfile", Ref(iam_instance_profile), Ref("AWS::NoValue")),
    AssociatePublicIpAddress=Ref(associate_public_ip_address),
    InstanceType=Ref(instance_type),
    UserData=make_user_data("""\
#!/bin/bash
# TODO add a header describing the overall idea and plan of improvement (proper cloud-init, etc.)
# default images mount the first ephemeral disk to /mnt
# this is from cloud-init config that comes with the cloud-init.rpm
umount /mnt
# set timezone
echo "UTC" > /etc/timezone
ln -sf /usr/share/zoneinfo/UTC /etc/localtime

# Base packages (required for cfn-init)
# kpartx and parted for detect and mount partition
yum install -y wget ruby ruby-devel kpartx parted

# Install mustache gem for easy templating
gem install mustache

# Pip
curl https://bootstrap.pypa.io/get-pip.py -o get-pip.py
python get-pip.py
# Downgrade pip to avoid https://github.com/pypa/pip/issues/3384
pip install "pip==8.1.0"

# aws-cli
pip install --upgrade "awscli==1.9.21"

# pip install awscli installs certify - that deprecates some crypto shit and things don't work well
# TODO check if upgrading this fixes it
pip uninstall -y certifi
pip install certifi==2015.04.28

# cfn bootstrap
curl -O https://s3.amazonaws.com/cloudformation-examples/aws-cfn-bootstrap-latest.tar.gz
tar -xzf aws-cfn-bootstrap-latest.tar.gz
cd aws-cfn*
easy_install pystache
python setup.py install

# Helper functions
function error_exit
{
  cfn-signal -e 1 -r "$1" 'Ref(WaitHandle)'
  exit 1
}

# Process CloudFormation init definitions
# TODO error_exist should signal an error to CF so that we can fail this instance
cfn-init -s Ref(AWS::StackName) -r BodyLaunchConfig  --region Ref(AWS::Region) || error_exit 'Failed to run cfn-init'

# export vars
echo "export number_of_disks=$(/usr/local/bin/detect-and-mount-disks)" >> /etc/profile.d/cellos.sh
source /etc/profile.d/cellos.sh

report_status "role ${cell_role}"
report_status "seeds ${cell_modules},zk_barrier"
report_status "${cell_role} start"

# install awslogs
curl https://s3.amazonaws.com/aws-cloudwatch/downloads/latest/awslogs-agent-setup.py -O
cat >> awslogs.conf <<-EOT
[general]
state_file = /var/awslogs/state/agent-state

[/var/log/cloud-init-output.log]
datetime_format = %Y-%m-%d %H:%M:%S
file = /var/log/cloud-init-output.log
buffer_duration = 5000
log_stream_name = ${full_cell_name}
initial_position = start_of_file
log_group_name = /var/log/cloud-init-output.log
EOT

python ./awslogs-agent-setup.py -r ${aws_region} -n -c awslogs.conf

# prepare roles
mkdir -p /opt/cell/etc/roles/
touch /opt/cell/etc/roles/${cell_role}

# prepare provisioning - cell specific
download_cell_profile() {
    mkdir -p /opt/cell/cluster/puppet/modules
    mkdir -p /opt/cell/puppet/profiles
    AWS_ACCESS_KEY_ID="${SAASBASE_ACCESS_KEY_ID}" AWS_SECRET_ACCESS_KEY="${SAASBASE_SECRET_ACCESS_KEY}" aws s3 cp ${repository}/cell-os/${cellos_version}.yaml /opt/cell/puppet/profiles
    # attempt to override the profile from the local bucket
    aws s3 cp s3://${cell_bucket_name}/${full_cell_name}/shared/cell-os/${cellos_version}.yaml /opt/cell/puppet/profiles/
    echo ${cellos_version} > /opt/cell/cluster/profile
    touch /opt/cell/cluster/cluster.yaml
}

# download cell profile so we can get the saasbase installer version
download_cell_profile

# download saasbase_installer (for now, we are expecting S3-based storage)
if [ ${repository:0:5} != "s3://" ]; then
  echo "The 'repository' var must point to an S3 bucket"
  exit 1
fi
saasbase_version=$(cat /opt/cell/puppet/profiles/${cellos_version}.yaml | yaml2json | jq -r '.["saasbase_deployment::version"]')
echo "saasbase_version=${saasbase_version}" >> /etc/profile.d/cellos.sh

curl -o /usr/local/bin/saasbase_installer https://s3.amazonaws.com/${repository:5}/saasbase_installer${saasbase_version}
chmod +x /usr/local/bin/saasbase_installer

AWS_ACCESS_KEY_ID="${SAASBASE_ACCESS_KEY_ID}" AWS_SECRET_ACCESS_KEY="${SAASBASE_SECRET_ACCESS_KEY}" bash /usr/local/bin/saasbase_installer -d /opt/cell fetch ${saasbase_version}
# provision seed
# we need to download the cell profile again, because saasbase_installer fetch
# overwrites all the files in /opt/cell/puppet/profiles
download_cell_profile
AWS_ACCESS_KEY_ID="${SAASBASE_ACCESS_KEY_ID}" AWS_SECRET_ACCESS_KEY="${SAASBASE_SECRET_ACCESS_KEY}" aws s3 cp ${repository}/cell-os/seed-${cellos_version}.tar.gz /opt/cell

# attempt to download seed from local bucket as well
aws s3 cp s3://$cell_bucket_name/${full_cell_name}/shared/cell-os/seed.tar.gz /opt/cell

####################### provision
mkdir -p /opt/cell/seed
pushd /opt/cell
rm -rf seed
[[ -f seed-${cellos_version}.tar.gz ]] && tar zxf seed-${cellos_version}.tar.gz
[[ -f seed.tar.gz ]] && tar zxf seed.tar.gz
rm -rf seed*.tar.gz
popd

function do_provision {
    local provision_script="${1}"
    for module_path in /opt/cell/seed/*; do
        local module="$(basename $module_path)"
        if [[ "$cell_modules" == *"${module}"* ]]; then
            if [[ -x "${module_path}/${provision_script}" ]]; then
                report_status "${module} start"
                "${module_path}/${provision_script}" || {
                    report_status "${module} failed"
                    error_exit "Failed to deploy ${module}"
                }
                report_status "${module} end"
            fi
        fi
    done
}

# execute pre
do_provision provision

# wait for zk
report_status "zk_barrier start"
/usr/local/bin/zk-barrier
export zk=`zk-list-nodes 2>/dev/null`
report_status "zk_barrier end"

# execute post
do_provision provision_post

report_status "${cell_role} end"

# All is well so signal success
cfn-signal -e 0 -r "Stack setup complete" "${aws_wait_handle}"

#EOF
""")
))

print(t.to_json(indent=2))
