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
from tropopause import *

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
    Default="cell-os-base-1.2-SNAPSHOT",
    Type="String",
    Description="cell-os bundle version",
))

SaasBaseDeploymentVersion = t.add_parameter(Parameter(
    "SaasBaseDeploymentVersion",
    Default="1.27",
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
    'us-west-2': {'AMI': 'ami-bd5b4f8d'}
})

t.add_condition(
    "RegionIsUsEast1", Equals(Ref("AWS::Region"), "us-east-1")
)

VPC = t.add_resource(ec2.VPC(
    "VPC",
    EnableDnsSupport=True,
    CidrBlock="10.0.0.0/16",
    EnableDnsHostnames=True,
    Tags=Tags(
        Application=Ref("AWS::StackId"),
    ),
))

# region domain is ec2.internal in us-east-1, REGION.compute.internal for
# others, according to
# http://docs.aws.amazon.com/AmazonVPC/latest/UserGuide/VPC_DHCP_Options.html
DHCP = t.add_resource(ec2.DHCPOptions(
    'DHCP',
    DomainName=If(
        "RegionIsUsEast1",
        "ec2.internal",
        Join("", [Ref("AWS::Region"), ".compute.internal"])
    ),
    DomainNameServers=['AmazonProvidedDNS']
))

VPCDHCPOptionsAssociation = t.add_resource(ec2.VPCDHCPOptionsAssociation(
    'DHCPAssoc',
    DhcpOptionsId=Ref("DHCP"),
    VpcId=Ref("VPC")
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

NucleusS3Policy = t.add_resource(iam.PolicyType(
    'NucleusS3Policy',
    PolicyName='NucleusS3Policy',
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
    ),
    Roles=[
        Ref("NucleusRole"),
    ]
))

def s3_ro_policy(name, roles, paths):
    resources = [Join("", ["arn:aws:s3:::", Ref(BucketName)])]
    resources.extend(
        [Join("", ["arn:aws:s3:::", Ref(BucketName), "/{}".format(path)]) for path in paths]
    )
    return iam.PolicyType(
        name,
        PolicyName=name,
        PolicyDocument=awacs.aws.Policy(
            Statement=[
                awacs.aws.Statement(
                    Effect=awacs.aws.Allow,
                    Resource=resources,
                    Action=[
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
                    ]
                )
            ]
        ),
        Roles=[Ref(role) for role in roles]
    )

MembraneReadOnlyPolicy = s3_ro_policy(
    "MembraneReadOnlyS3Policy",
    ["MembraneRole"],
    ["membrane/*"]
)
t.add_resource(MembraneReadOnlyPolicy)
StatelessBodyReadOnlyPolicy = s3_ro_policy(
    "StatelessBodyReadOnlyS3Policy",
    ["StatelessBodyRole"],
    ["stateless-body/*"]
)
t.add_resource(StatelessBodyReadOnlyPolicy)
StatefulBodyReadOnlyPolicy = s3_ro_policy(
    "StatefulBodyReadOnlyS3Policy",
    ["StatefulBodyRole"],
    ["stateful-body/*"]
)
t.add_resource(StatefulBodyReadOnlyPolicy)
SharedReadOnlyPolicy = s3_ro_policy(
    "SharedReadOnlyS3Policy",
    ["StatelessBodyRole", "StatefulBodyRole", "MembraneRole"],
    ["shared/*"]
)
t.add_resource(SharedReadOnlyPolicy)

NucleusEc2Policy = t.add_resource(iam.PolicyType(
    'NucleusEc2Policy',
    PolicyName='NucleusEc2Policy',
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
    ),
    Roles=[
        Ref("NucleusRole"),
        Ref("StatefulBodyRole")
    ]
))

NucleusCfnPolicy = t.add_resource(iam.PolicyType(
    'NucleusCfnPolicy',
    PolicyName='NucleusCfnPolicy',
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
    ),
    Roles=[
        Ref("NucleusRole"),
        Ref("StatefulBodyRole")
    ]
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
    Path='/'
))

NucleusInstanceProfile = t.add_resource(iam.InstanceProfile(
    "NucleusInstanceProfile",
    Path="/",
    Roles=[Ref(NucleusRole)],
))

MembraneRole = t.add_resource(iam.Role(
    "MembraneRole",
    AssumeRolePolicyDocument=awacs.aws.Policy(
        Statement=[
            awacs.aws.Statement(
                Effect=awacs.aws.Allow,
                Principal=awacs.aws.Principal(principal='Service', resources=['ec2.amazonaws.com']),
                Action=[awacs.sts.AssumeRole]
            )
        ]
    ),
    Path='/'
))

MembraneInstanceProfile = t.add_resource(iam.InstanceProfile(
    "MembraneInstanceProfile",
    Path="/",
    Roles=[Ref(MembraneRole)],
))

StatelessBodyRole = t.add_resource(iam.Role(
    "StatelessBodyRole",
    AssumeRolePolicyDocument=awacs.aws.Policy(
        Statement=[
            awacs.aws.Statement(
                Effect=awacs.aws.Allow,
                Principal=awacs.aws.Principal(principal='Service', resources=['ec2.amazonaws.com']),
                Action=[awacs.sts.AssumeRole]
            )
        ]
    ),
    Path='/'
))

StatelessBodyInstanceProfile = t.add_resource(iam.InstanceProfile(
    "StatelessBodyInstanceProfile",
    Path="/",
    Roles=[Ref(StatelessBodyRole)],
))

StatefulBodyRole = t.add_resource(iam.Role(
    "StatefulBodyRole",
    AssumeRolePolicyDocument=awacs.aws.Policy(
        Statement=[
            awacs.aws.Statement(
                Effect=awacs.aws.Allow,
                Principal=awacs.aws.Principal(principal='Service', resources=['ec2.amazonaws.com']),
                Action=[awacs.sts.AssumeRole]
            )
        ]
    ),
    Path='/'
))

StatefulBodyInstanceProfile = t.add_resource(iam.InstanceProfile(
    "StatefulBodyInstanceProfile",
    Path="/",
    Roles=[Ref(StatefulBodyRole)],
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
ingress 127.127.98.227/32 tcp 0:65535
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

def create_cellos_substack(t, name=None, role=None, cell_modules=None, tags=[], security_groups=[], load_balancers=[], instance_profile=None):
    params = {
        "Role": role,
        "Tags": tags,
        "CellModules": cell_modules,
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

    substack_template_url = Join("", ["https://s3.amazonaws.com/", Ref("BucketName"), "/", Ref("BodyStackTemplate")])
    # check if the template url is overridden (e.g. with a release one)
    if len(sys.argv) > 1 and len(sys.argv[1]) > 7 :
        substack_template_url = sys.argv[1]

    t.add_resource(cfn.Stack(
        name + "Stack",
        TemplateURL=substack_template_url,
        TimeoutInMinutes="10",
        Parameters=params
    ))

create_cellos_substack(
    t,
    name="Nucleus",
    role="nucleus",
    cell_modules="00-docker,00-java,01-exhibitor,10-hdfs-raw,99-cell",
    tags="nucleus",
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
    cell_modules="00-docker,02-mesos,99-cell",
    tags="membrane,slave,body",
    instance_profile="MembraneInstanceProfile",
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
    cell_modules="00-docker,00-java,01-exhibitor,02-mesos,10-marathon,99-cell",
    tags="slave,body,stateless,stateless-body",
    instance_profile="StatelessBodyInstanceProfile",
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
    cell_modules="00-docker,00-java,02-mesos,10-hdfs-raw,99-cell",
    tags="slave,body,stateful,stateful-body",
    instance_profile="StatefulBodyInstanceProfile",
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
