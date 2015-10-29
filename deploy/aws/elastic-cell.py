import sys
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
from troposphere_helpers import *

from troposphere import Not, Ref, Equals, If, Tags
from troposphere import Base64, Select, FindInMap, GetAtt, GetAZs, Join, Output
from troposphere import Parameter, Ref, Tags, Template

t = Template()

t.add_version("2010-09-09")

t.add_description("""\
cell-os-base - https://git.corp.adobe.com/metal-cell/cell-os""")

InstanceType = t.add_parameter(Parameter(
    "InstanceType",
    Default="c3.2xlarge",
    ConstraintDescription="must be a valid, HVM-compatible EC2 instance type.",
    Type="String",
    Description="EC2 instance type",
    AllowedValues=[
        "t2.micro", "t2.small", "t2.medium", "t2.large",
        "m3.medium", "m3.large", "m3.xlarge", "m3.2xlarge",
        "c4.large", "c4.xlarge", "c4.2xlarge", "c4.4xlarge", "c4.8xlarge",
        "c3.large", "c3.xlarge", "c3.2xlarge", "c3.4xlarge", "c3.8xlarge",
        "r3.large", "r3.xlarge", "r3.2xlarge", "r3.4xlarge", "r3.8xlarge",
        "i2.xlarge", "i2.2xlarge", "i2.4xlarge", "i2.8xlarge",
        "hs1.8xlarge", "g2.2xlarge"
    ],
))

InstanceTypeStatefulBody = t.add_parameter(Parameter(
    "InstanceTypeStatefulBody",
    Default="c3.2xlarge",
    ConstraintDescription="must be a valid, HVM-compatible EC2 instance type.",
    Type="String",
    Description="EC2 instance type",
    AllowedValues=[
        "c3.large", "c3.xlarge", "c3.2xlarge", "c3.4xlarge", "c3.8xlarge",
        "cc2.8xlarge",
        "cr1.8xlarge",
        "d2.xlarge", "d2.2xlarge", "d2.4xlarge", "d2.8xlarge",
        "g2.2xlarge", "g2.8xlarge",
        "hi1.4xlarge",
        "hs1.8xlarge",
        "i2.xlarge", "i2.2xlarge", "i2.4xlarge", "i2.8xlarge",
        "m3.medium", "m3.large", "m3.xlarge", "m3.2xlarge",
        "r3.large", "r3.xlarge", "r3.2xlarge", "r3.4xlarge", "r3.8xlarge"
    ],
))

CellName = t.add_parameter(Parameter(
    "CellName",
    Default="cell-1",
    Type="String",
    Description="The name of this cell (e.g. cell-1). This will get prefixed with account id and region to get the full cell id.",
))

CellOsVersionBundle = t.add_parameter(Parameter(
    "CellOsVersionBundle",
    Default="cell-os-base-1.1-SNAPSHOT",
    Type="String",
    Description="cell-os bundle version",
))

SaasBaseDeploymentVersion = t.add_parameter(Parameter(
    "SaasBaseDeploymentVersion",
    Default="1.26",
    Type="String",
    Description="saasbase-deployment version",
))

KeyName = t.add_parameter(Parameter(
    "KeyName",
    Type="AWS::EC2::KeyPair::KeyName",
    Description="Existing EC2 KeyPair to be associated with all cluster instances for SSH access. The default user is 'centos'",
))

NucleusSize = t.add_parameter(Parameter(
    "NucleusSize",
    Default="3",
    Type="Number",
    Description="Number of nodes in the cell nucleus",
))

StatelessBodySize = t.add_parameter(Parameter(
    "StatelessBodySize",
    Default="1",
    Type="Number",
    Description="Number of nodes in the cell stateless body",
))

StatefulBodySize = t.add_parameter(Parameter(
    "StatefulBodySize",
    Default="1",
    Type="Number",
    Description="Number of nodes in the cell stateful body (local disk access)",
))

MembraneSize = t.add_parameter(Parameter(
    "MembraneSize",
    Default="1",
    Type="Number",
    Description="Number of nodes in the cell membrane, which is publicly exposed",
))

BucketName = t.add_parameter(Parameter(
    "BucketName",
    Type="String",
    Description="Cell's S3 bucket name. Used for metadata and backups. Can be one per account as we prefix data with cell name inside",
))

SaasBaseAccessKeyId = t.add_parameter(Parameter(
    "SaasBaseAccessKeyId",
    Type="String",
    Description="SaasBase S3 repo read-only AWS account Access Key ID (http://saasbase.corp.adobe.com/ops/operations/deployment.html)",
))

SaasBaseSecretAccessKey = t.add_parameter(Parameter(
    "SaasBaseSecretAccessKey",
    Type="String",
    Description="SaasBase S3 repo read-only AWS account Secret Access Key (http://saasbase.corp.adobe.com/ops/operations/deployment.html)",
))

BodyStackTemplate = t.add_parameter(Parameter(
    "BodyStackTemplate",
    Default="elastic-cell-scaling-group.json",
    Type="String",
    Description="",
))

t.add_mapping("RegionMap", {
    'ap-northeast-1': {'AMI': 'ami-24f47024'},
    'ap-southeast-1': {'AMI': 'ami-3e9e906c'},
    'ap-southeast-2': {'AMI': 'ami-f54d0fcf'},
    'eu-central-1': {'AMI': 'ami-649d9a79'},
    'eu-west-1': {'AMI': 'ami-e2580795'},
    'sa-east-1': {'AMI': 'ami-476ae25a'},
    'us-east-1': {'AMI': 'ami-11b7017a'},
    'us-west-1': {'AMI': 'ami-37a45d73'},
    'us-west-2': {'AMI': 'ami-bd5b4f8d'}}
)

t.add_mapping("UserData", {
    'config': {
        'base': split_content("""
### Minimal inline cluster.yaml
echo docker::version: 1.7.1                  >> /root/cluster/cluster.yaml
"""),
        'mesos': split_content("""
echo mesos::zookeeper:   zk://$zk/mesos      >> /root/cluster/cluster.yaml
"""),
        'marathon': split_content("""
echo marathon::zk:       zk://$zk/marathon   >> /root/cluster/cluster.yaml
echo marathon::master:   zk://$zk/mesos      >> /root/cluster/cluster.yaml
echo marathon::bin_path: /opt/marathon/bin   >> /root/cluster/cluster.yaml
echo marathon::install_java: false           >> /root/cluster/cluster.yaml
"""),
        'zookeeper': split_content("""
echo "zookeeper::aws_s3_region: ${aws_region}" >> /root/cluster/cluster.yaml
echo "zookeeper::aws_s3_bucket: ${cell_bucket_name}" >> /root/cluster/cluster.yaml
echo "zookeeper::aws_s3_prefix: ${cell_name}/nucleus/exhibitor" >> /root/cluster/cluster.yaml
"""),
    'hadoop': split_content("""
echo "" >> /root/cluster/cluster.yaml
### HDFS setup
echo hadoop_version: 2.6.0-cdh5.4.2-adobe    >> /root/cluster/cluster.yaml
echo "hadoop_lzo_version: 0.4.20" >> /root/cluster/cluster.yaml
export nn1_host=$(eval $search_instance_cmd Name=tag:role,Values=nucleus | jq -r '.[][][1]' | head -n 1)
export nn2_host=$(eval $search_instance_cmd Name=tag:role,Values=nucleus | jq -r '.[][][1]' | head -2 | tail -1)
echo "nn1_host: ${nn1_host}" >> /root/cluster/cluster.yaml
echo "nn2_host: ${nn2_host}" >> /root/cluster/cluster.yaml
echo "zk_quorum:" >> /root/cluster/cluster.yaml
zk-list-nodes | sed 's/,/\\n/g' | sed 's/:.*$//g' | sed 's/^/-  /' >> /root/cluster/cluster.yaml
echo "hadoop_data_nodes: []" >> /root/cluster/cluster.yaml
echo "hadoop_number_of_disks: $(/usr/local/bin/detect-and-mount-disks)" >> /root/cluster/cluster.yaml
echo "hadoop::historyserver_host: $nn1_host" >> /root/cluster/cluster.yaml
echo "hadoop::proxyusers: {}" >> /root/cluster/cluster.yaml
echo "hadoop_data_nodes: []" >> /root/cluster/cluster.yaml
""")
    },
    'provision': {
        "pre": split_content("""\
provision puppet ${pre_zk_modules}
"""),
        'post': split_content("""\
provision puppet ${post_zk_modules}
"""),
    },
    'orchestrate': {
        'namenode': split_content("""\
export host=$(hostname -f)
service hadoop-hdfs-journalnode start
sleep 10
aws s3api put-object --bucket ${cell_bucket_name} --key orch/${aws_parent_stack_name}/zk/$host
if [[ $host == $nn1_host ]]; then
  aws_wait "aws s3api list-objects --bucket ${cell_bucket_name} --prefix orch/${aws_parent_stack_name}/zk/" ".Contents | length" "3"
  su --login hadoop -c "/home/hadoop/hadoop/bin/hdfs namenode -format -nonInteractive"
  su --login hadoop -c "/home/hadoop/hadoop/bin/hdfs zkfc -formatZK -nonInteractive"
  systemctl start hadoop-hdfs-zkfc
  systemctl start hadoop-hdfs-namenode
  aws s3api put-object --bucket ${cell_bucket_name} --key orch/${aws_parent_stack_name}/nn1
fi

if [[ $host == $nn2_host ]]; then
  aws_wait "aws s3api list-objects --bucket ${cell_bucket_name} --prefix orch/${aws_parent_stack_name}/zk/" ".Contents | length" "3"
  aws_wait "aws s3api list-objects --bucket ${cell_bucket_name} --prefix orch/${aws_parent_stack_name}/nn1" ".Contents | length" "1"
  su --login hadoop -c "/home/hadoop/hadoop/bin/hdfs namenode -bootstrapStandby -nonInteractive"
  systemctl start hadoop-hdfs-zkfc
  systemctl start hadoop-hdfs-namenode
  sleep 10
  aws s3api put-object --bucket ${cell_bucket_name} --key orch/${aws_parent_stack_name}/nn2
fi
"""),
        'datanode': split_content("""\
aws_wait "aws s3api list-objects --bucket ${cell_bucket_name} --prefix orch/${aws_parent_stack_name}/nn2" ".Contents | length" "1"
systemctl start hadoop-hdfs-datanode
aws s3api put-object --bucket ${cell_bucket_name} --key orch/${aws_parent_stack_name}/dn/${host}
"""),
    }
})

VPC = t.add_resource(ec2.VPC(
    "VPC",
    EnableDnsSupport=True,
    CidrBlock="10.0.0.0/16",
    EnableDnsHostnames=True,
    Tags=Tags(
        Application=Ref("AWS::StackId"),
    ),
))

Subnet = t.add_resource(ec2.Subnet(
    "Subnet",
    VpcId=Ref("VPC"),
    CidrBlock="10.0.0.0/24",
    Tags=Tags(
        Application=Ref("AWS::StackId"),
    ),
))

InternetGateway = t.add_resource(ec2.InternetGateway(
    "InternetGateway",
    Tags=Tags(
        Application=Ref("AWS::StackId"),
    ),
))

AttachGateway = t.add_resource(ec2.VPCGatewayAttachment(
    "AttachGateway",
    VpcId=Ref(VPC),
    InternetGatewayId=Ref("InternetGateway")
))

RouteTable = t.add_resource(ec2.RouteTable(
    "RouteTable",
    VpcId=Ref(VPC),
    Tags=Tags(
        Application=Ref("AWS::StackId"),
    ),
))

Route = t.add_resource(ec2.Route(
    "Route",
    GatewayId=Ref(InternetGateway),
    DestinationCidrBlock="0.0.0.0/0",
    RouteTableId=Ref("RouteTable"),
    DependsOn="AttachGateway",
))

SubnetRouteTableAssociation = t.add_resource(ec2.SubnetRouteTableAssociation(
    "SubnetRouteTableAssociation",
    SubnetId=Ref(Subnet),
    RouteTableId=Ref("RouteTable"),
))

NucleusRole = t.add_resource(iam.Role(
    "NucleusRole",
    AssumeRolePolicyDocument=awacs.aws.Policy(
        Statement=[
            awacs.aws.Statement(
                Effect=awacs.aws.Allow,
                Principal=awacs.aws.Principal(principal='Service', resources=['ec2.amazonaws.com']),
                Action=[awacs.sts.AssumeRole]
            )
        ]
    ),
    Policies=[
        iam.Policy(
            PolicyName="s3_nucleus",
            PolicyDocument=awacs.aws.Policy(
                Statement=[
                    awacs.aws.Statement(
                        Effect=awacs.aws.Allow,
                        Resource=[
                            Join("", ["arn:aws:s3:::", Ref(BucketName), "/*"]),
                            Join("", ["arn:aws:s3:::", Ref(BucketName)])
                        ],
                        Action=[
                            awacs.aws.Action("s3", "AbortMultipartUpload"),
                            awacs.aws.Action("s3", "DeleteObject"),
                            awacs.aws.Action("s3", "GetBucketAcl"),
                            awacs.aws.Action("s3", "GetBucketPolicy"),
                            awacs.aws.Action("s3", "GetObject"),
                            awacs.aws.Action("s3", "GetObjectAcl"),
                            awacs.aws.Action("s3", "GetObjectVersion"),
                            awacs.aws.Action("s3", "GetObjectVersionAcl"),
                            awacs.aws.Action("s3", "ListBucket"),
                            awacs.aws.Action("s3", "ListBucketMultipartUploads"),
                            awacs.aws.Action("s3", "ListBucketVersions"),
                            awacs.aws.Action("s3", "ListMultipartUploadParts"),
                            awacs.aws.Action("s3", "PutObject"),
                            awacs.aws.Action("s3", "PutObjectAcl"),
                            awacs.aws.Action("s3", "PutObjectVersionAcl")
                        ]
                    )
                ]
            )
        ),
        iam.Policy(
            PolicyName="ec2_nucleus",
            PolicyDocument=awacs.aws.Policy(
                Statement=[
                    awacs.aws.Statement(
                        Effect=awacs.aws.Allow,
                        Resource=["*"],
                        Action=[
                            awacs.aws.Action("ec2", "Describe*"),
                        ]
                    )
                ]
            )
        ),
        iam.Policy(
            PolicyName="cfn_nucleus",
            PolicyDocument=awacs.aws.Policy(
                Statement=[
                    awacs.aws.Statement(
                        Effect=awacs.aws.Allow,
                        Resource=["*"],
                        Action=[
                            awacs.aws.Action("autoscaling", "Describe*"),
                            awacs.aws.Action("cloudformation", "Describe*"),
                            awacs.aws.Action("cloudformation", "GetStackPolicy"),
                            awacs.aws.Action("cloudformation", "GetTemplate*"),
                            awacs.aws.Action("cloudformation", "ListStacks"),
                            awacs.aws.Action("cloudformation", "ListStackResources"),
                        ]
                    )
                ]
            )
        ),

    ],
    Path='/'
))

NucleusInstanceProfile = t.add_resource(iam.InstanceProfile(
    "NucleusInstanceProfile",
    Path="/",
    Roles=[Ref(NucleusRole)],
))

BodySecurityGroup = t.add_resource(security_group(
    'BodySecurityGroup',
    """
ingress LbSecurityGroup tcp 80:80
ingress LbSecurityGroup tcp 5050:5050
ingress LbSecurityGroup tcp 8080:8080
ingress LbSecurityGroup tcp 8181:8181
    """,
    VPC,
    description="All nodes in body. Grants access to LbSecurityGroup"
))

NucleusSecurityGroup = t.add_resource(security_group(
    'NucleusSecurityGroup',
    """
ingress LbSecurityGroup tcp 8181:8181
ingress BodySecurityGroup tcp 2181:2181
ingress BodySecurityGroup tcp 2888:2888
ingress BodySecurityGroup tcp 3888:3888
ingress BodySecurityGroup tcp 9000:9001
ingress BodySecurityGroup tcp 50000:50100
    """,
    VPC,
    description="All nucleus nodes. Grants access to Exhibitor, ZK ports from LB and Body SG, respectively"
))

ExternalWhitelistSecurityGroup = t.add_resource(security_group(
    'ExternalWhitelistSecurityGroup',
    """
ingress 127.127.0.0/16 tcp 0:65535
ingress 127.127.216.100/32 tcp 0:65535
ingress 127.127.198.0/24 tcp 0:65535
ingress 127.127.140.131/32 tcp 0:65535
ingress 127.127.18.225/24 tcp 0:65535
    """,
    VPC,
    description="All nodes are part of it. Grants access to some Adobe CIDRs. Email to metal-cell@adobe.com"
))

LbSecurityGroup = t.add_resource(ec2.SecurityGroup(
    "LbSecurityGroup",
    GroupDescription="Enable Exhibitor access",
    VpcId=Ref(VPC)
))

PublicSecurityGroup = t.add_resource(security_group(
    'PublicSecurityGroup',
    """
ingress 0.0.0.0/0 tcp 80:80
ingress 0.0.0.0/0 tcp 443:443
    """,
    VPC,
    description="Public access for all nodes in this group. Tread carefully."
))

BodyToLbSecurityGroupIngressToAvoidCircularDeps = t.add_resource(ec2.SecurityGroupIngress(
    "BodyToLbSecurityGroupIngressToAvoidCircularDeps",
    GroupId=Ref("LbSecurityGroup"),
    SourceSecurityGroupId=Ref("BodySecurityGroup"),
    IpProtocol="tcp",
    FromPort="0",
    ToPort="65535",
))

NucleusToLbSecurityGroupIngressToAvoidCircularDeps = t.add_resource(ec2.SecurityGroupIngress(
    "NucleusToLbSecurityGroupIngressToAvoidCircularDeps",
    GroupId=Ref("LbSecurityGroup"),
    SourceSecurityGroupId=Ref("NucleusSecurityGroup"),
    IpProtocol="tcp",
    FromPort="80",
    ToPort="80",
))

NucleusToNucleusSecurityGroupIngressToAvoidCircularDeps = t.add_resource(ec2.SecurityGroupIngress(
    "NucleusToNucleusSecurityGroupIngressToAvoidCircularDeps",
    GroupId=Ref("NucleusSecurityGroup"),
    SourceSecurityGroupId=Ref("NucleusSecurityGroup"),
    IpProtocol="tcp",
    FromPort="0",
    ToPort="65535",
))

BodyToBodySecurityGroupIngressToAvoidCircularDeps = t.add_resource(ec2.SecurityGroupIngress(
    "BodyToBodySecurityGroupIngressToAvoidCircularDeps",
    GroupId=Ref("BodySecurityGroup"),
    SourceSecurityGroupId=Ref("BodySecurityGroup"),
    IpProtocol="tcp",
    FromPort="0",
    ToPort="65535",
))

def create_load_balancer(t, name, instance_port, target):
    return t.add_resource(elb.LoadBalancer(
        name + "LoadBalancer",
        LoadBalancerName=Join("", [Ref(CellName), "-lb-" + name.lower()]),
        CrossZone="true",
        Scheme="internal",
        SecurityGroups=[Ref("LbSecurityGroup")],
        Subnets=[Ref(Subnet)],
        Listeners=[{
            "InstancePort": str(instance_port),
            "LoadBalancerPort": "80",
            "Protocol": "HTTP"
        }],
        HealthCheck=elb.HealthCheck(
            HealthyThreshold="3",
            Interval="30",
            Target="HTTP:%d%s" % (instance_port, target),
            Timeout="5",
            UnhealthyThreshold="5",
        ),
        Tags=Tags(
            cell=Ref(CellName),
        ),
    ))


MarathonLoadBalancer = create_load_balancer(t,
    "Marathon",
    8080,
    "/status"
)

ZookeeperLoadBalancer = create_load_balancer(t,
    "Zookeeper",
    8181,
    "/exhibitor/v1/cluster/state"
)

MesosLoadBalancer = create_load_balancer(t,
    "Mesos",
    5050,
    "/health"
)

MembraneLoadBalancer = create_load_balancer(t,
    "Membrane",
    80,
    "/health-check"
)

WaitHandle = t.add_resource(cfn.WaitConditionHandle("WaitHandle",))

def create_cellos_substack(t, name=None, role=None, pre_zk_modules=None, post_zk_modules=None, tags=[], user_data=[], user_data_post=[], security_groups=[], load_balancers=[], instance_profile=None):
    params = {
        "Role": role,
        "Tags": tags,
        "PreZkModules": pre_zk_modules,
        "PostZkModules": post_zk_modules,
        "SaasBaseUserData": Join("", user_data),
        "SaasBaseUserDataPost": Join("", user_data_post),
        "SecurityGroups": Join(",", security_groups),
        "LoadBalancerNames": Join(",", load_balancers),
        "ZookeeperLoadBalancer": GetAtt("ZookeeperLoadBalancer", "DNSName"),
        "AssociatePublicIpAddress": "true",
        "GroupSize": Ref(name + "Size"),
        "ImageId": FindInMap("RegionMap", Ref("AWS::Region"), "AMI"),
        "CellName": Ref("CellName"),
        "BucketName": Ref("BucketName"),
        "CellOsVersionBundle": Ref("CellOsVersionBundle"),
        "InstanceType": Ref("InstanceType"),
        "Subnet": Ref("Subnet"),
        "KeyName": Ref("KeyName"),
        "SaasBaseDeploymentVersion": Ref("SaasBaseDeploymentVersion"),
        "SaasBaseSecretAccessKey": Ref("SaasBaseSecretAccessKey"),
        "SaasBaseAccessKeyId": Ref("SaasBaseAccessKeyId"),
        "ParentStackName": Ref("AWS::StackName"),
        "WaitHandle": Ref("WaitHandle"),
    }
    if instance_profile != None:
        params["IamInstanceProfile"] = Ref(instance_profile)

    t.add_resource(cfn.Stack(
        name + "Stack",
        TemplateURL=Join("", ["https://s3.amazonaws.com/", Ref("BucketName"), "/", Ref("BodyStackTemplate")]),
        TimeoutInMinutes="10",
        Parameters=params
    ))

create_cellos_substack(
    t,
    name="Nucleus",
    role="nucleus",
    pre_zk_modules="docker,zookeeper,java",
    post_zk_modules="mesos::slave,base,hadoop_2_namenode,hadoop_2,hadoop_2_journalnode",
    tags="nucleus",
    user_data=[
        Join("", FindInMap("UserData", "config", "base")),
        Join("", FindInMap("UserData", "config", "zookeeper")),
        Join("", FindInMap("UserData", "provision", "pre")),
    ],
    user_data_post=[
        Join("", FindInMap("UserData", "config", "base")),
        Join("", FindInMap("UserData", "config", "zookeeper")),
        Join("", FindInMap("UserData", "config", "hadoop")),
        Join("", FindInMap("UserData", "provision", "post")),
        Join("", FindInMap("UserData", "orchestrate", "namenode")),
    ],
    instance_profile="NucleusInstanceProfile",
    security_groups=[
        Ref(NucleusSecurityGroup),
        Ref(ExternalWhitelistSecurityGroup)
    ],
    load_balancers=[Ref("ZookeeperLoadBalancer")],
)

create_cellos_substack(
    t,
    name="Membrane",
    role="membrane",
    pre_zk_modules="docker",
    post_zk_modules="mesos::slave",
    tags="membrane,slave,body",
    user_data=[
        Join("", FindInMap("UserData", "config", "base")),
        Join("", FindInMap("UserData", "config", "mesos")),
        Join("", FindInMap("UserData", "provision", "pre")),
    ],
    user_data_post=[
        Join("", FindInMap("UserData", "config", "base")),
        Join("", FindInMap("UserData", "config", "mesos")),
        Join("", FindInMap("UserData", "provision", "pre")),
    ],
    security_groups=[
        Ref(PublicSecurityGroup),
        Ref(BodySecurityGroup),
        Ref(ExternalWhitelistSecurityGroup)
    ],
    load_balancers=[
        Ref("MembraneLoadBalancer")
    ]
)

create_cellos_substack(
    t,
    name="StatelessBody",
    role="stateless-body",
    pre_zk_modules="docker,java",
    post_zk_modules="mesos::master,mesos::slave,marathon",
    tags="slave,body,stateless,stateless-body",
    user_data=[
        Join("", FindInMap("UserData", "config", "base")),
        Join("", FindInMap("UserData", "config", "mesos")),
        Join("", FindInMap("UserData", "config", "marathon")),
        Join("", FindInMap("UserData", "provision", "pre")),
    ],
    user_data_post=[
        Join("", FindInMap("UserData", "config", "base")),
        Join("", FindInMap("UserData", "config", "mesos")),
        Join("", FindInMap("UserData", "config", "marathon")),
        Join("", FindInMap("UserData", "provision", "post")),
    ],
    security_groups=[
        Ref(BodySecurityGroup),
        Ref(ExternalWhitelistSecurityGroup)
    ],
    load_balancers=[
        Ref("MesosLoadBalancer"),
        Ref("MarathonLoadBalancer")
    ]
)

create_cellos_substack(
    t,
    name="StatefulBody",
    role="stateful-body",
    pre_zk_modules="docker,java",
    post_zk_modules="mesos::slave,base,hadoop_2_datanode",
    tags="slave,body,stateful,stateful-body",
    user_data=[
        Join("", FindInMap("UserData", "config", "base")),
        Join("", FindInMap("UserData", "config", "mesos")),
        Join("", FindInMap("UserData", "config", "marathon")),
        Join("", FindInMap("UserData", "provision", "pre")),
    ],
    user_data_post=[
        Join("", FindInMap("UserData", "config", "base")),
        Join("", FindInMap("UserData", "config", "mesos")),
        Join("", FindInMap("UserData", "config", "marathon")),
        Join("", FindInMap("UserData", "config", "hadoop")),
        Join("", FindInMap("UserData", "provision", "post")),
        Join("", FindInMap("UserData", "orchestrate", "datanode")),
    ],
    instance_profile="NucleusInstanceProfile",
    security_groups=[
        Ref(BodySecurityGroup),
        Ref(ExternalWhitelistSecurityGroup)
    ],
    load_balancers=[
        Ref("MesosLoadBalancer"),
        Ref("MarathonLoadBalancer")
    ]
)

print(t.to_json(indent=2))
