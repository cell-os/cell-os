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

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email import charset
charset.add_charset('utf-8', charset.SHORTEST)

DIR = os.path.dirname(os.path.realpath(__file__))


def make_multi_part_user_data(cloud_config, user_data):
    """
    Creates an AWS multi-part user data packages
    http://cloudinit.readthedocs.org/en/latest/topics/format.html
    Reads 2 files:
        - cloud-config - this is an yaml cloud-init configuration
        (http://cloudinit.readthedocs.org/en/latest/topics/examples.html)
        - user-data script
    """
    combined_message = MIMEMultipart()
    for f in [
        (cloud_config, "cloud-config", "cloud-config"),
        (user_data, "x-shellscript", "user-data.sh")
    ]:
        if f[0] is None:
            continue
        content = readify(f[0])
        mime_type = f[1]
        attachment = f[2]
        message = MIMEText(content, mime_type, "utf-8")
        message.add_header("Content-Disposition",
                           "attachment; filename={}".format(attachment))
        combined_message.attach(message)
    tmp = str(combined_message)
    return make_user_data(tmp)

t = Template()

t.add_version("2010-09-09")

t.add_description("""\
cell-os-base - https://git.corp.adobe.com/metal-cell/cell-os""")
instance_type = t.add_parameter(Parameter(
    "InstanceType",
    ConstraintDescription="must be a valid, HVM-compatible EC2 instance type.",
    Type="String",
    Description="EC2 instance type",
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
t.add_condition(
    "HasLbs", Not(Equals(Join("", Ref(load_balancer_names)), ""))
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
    LoadBalancerNames=If("HasLbs", Ref(load_balancer_names), []),
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

user_data = """#!/bin/bash
curl https://bootstrap.pypa.io/get-pip.py -o get-pip.py
python get-pip.py
pip install "pip==8.1.0"
pip install --upgrade "awscli==1.9.21"
pip uninstall -y certifi
pip install certifi==2015.04.28 pyyaml pystache

# cfn bootstrap
curl -O https://s3.amazonaws.com/cloudformation-examples/aws-cfn-bootstrap-latest.tar.gz
tar -xzf aws-cfn-bootstrap-latest.tar.gz
cd aws-cfn*
python setup.py install

# Helper functions
function error_exit
{
  cfn-signal -e 1 -r "$1" 'Ref(WaitHandle)'
  exit 1
}

# Process CloudFormation init definitions
# TODO error_exit should signal an error to CF so that we can fail this instance
cfn-init -s "Ref(AWS::StackName)" -r BodyLaunchConfig  --region "Ref(AWS::Region)" || error_exit 'Failed to run cfn-init'
source /etc/profile.d/cellos.sh
mkdir -p /opt/cell/
aws s3 cp s3://${cell_bucket_name}/${full_cell_name}/shared/cell-os/user-data /opt/cell/
chmod +x /opt/cell/user-data
/opt/cell/user-data
"""

BodyLaunchConfig = t.add_resource(asn.LaunchConfiguration(
    "BodyLaunchConfig",
    Metadata=cfn.Init({
        "config": cfn.InitConfig(
            files=cfn.InitFiles({
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
    UserData=make_multi_part_user_data(None, user_data)
))

print(t.to_json(indent=2))
