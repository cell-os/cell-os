#!/bin/bash

# get the absolute path of the executable
SELF_PATH=$(cd -P -- "$(dirname -- "$0")" && pwd -P) && SELF_PATH=$SELF_PATH/$(basename -- "$0")
# resolve symlinks
while [ -h $SELF_PATH ]; do
  # 1) cd to directory of the symlink
  # 2) cd to the directory of where the symlink points
  # 3) get the pwd
  # 4) append the basename
  DIR=$(dirname -- "$SELF_PATH")
  SYM=$(readlink $SELF_PATH)
  SELF_PATH=$(cd $DIR && cd $(dirname -- "$SYM") && pwd)/$(basename -- "$SYM")
done
DIR=$(dirname $SELF_PATH)
# cell-os cli
type aws >/dev/null 2>&1 || {
  cat >&2 <<EOD
AWS CLI not found
pip install awscli
see http://docs.aws.amazon.com/cli/latest/userguide/installing.html
EOD

exit 1
}

VERSION=${VERSION:-$(cat VERSION)}
SAASBASE_ACCESS_KEY_ID="${SAASBASE_ACCESS_KEY_ID:-XXXXXXXXXXXXXXXXXXXX}"
SAASBASE_SECRET_ACCESS_KEY="${SAASBASE_SECRET_ACCESS_KEY:-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx}"
AWS_OPTIONS='--no-paginate --output text'
PROXY_PORT=${PROXY_PORT:-'1234'}
SSH_TIMEOUT=${SSH_TIMEOUT:-'5'} # seconds
SSH_USER=${SSH_USER:-'centos'} # used to login on instances, specific to VM image

usage() {
cat >&2 <<EOD

 ██████╗███████╗██╗     ██╗             ██████╗  ███████╗     ██╗    ██████╗ 
██╔════╝██╔════╝██║     ██║            ██╔═══██╗ ██╔════╝    ███║    ╚════██╗
██║     █████╗  ██║     ██║     █████╗ ██║   ██║ ███████╗    ╚██║     █████╔╝
██║     ██╔══╝  ██║     ██║     ╚════╝ ██║   ██║ ╚════██║     ██║    ██╔═══╝ 
╚██████╗███████╗███████╗███████╗       ╚██████╔╝ ███████║     ██║██╗ ███████╗
 ╚═════╝╚══════╝╚══════╝╚══════╝        ╚═════╝  ╚══════╝     ╚═╝╚═╝ ╚══════╝

cell-os cli ${VERSION}

usage: ./cell <action> <cell-name> [arguments ...]
  actions:
    build <cell-name> <substack-template-url> - builds CF templates
          the substack-template-url is the full URL where the nested stack template will be found
          e.g. "https://s3.amazonaws.com/saasbase-repo/cell-os/deploy/aws/elastic-cell-scaling-group-1.1.json"
    create <cell-name> - creates a new cell
    update <cell-name> - updates an existing cell
    delete <cell-name> - deletes an existing cell
    list <cell-name> - lists existing stacks or the nodes in a cell
    scale <cell-name> <role> <capacity> - scales role to desired capacity
    ssh <cell-name> <role> [<index>] - ssh to first node in role or to index
    i2cssh <cell-name> [<role>] - ssh to nodes in a role, or to all nodes if no role provided
    log <cell-name> [<role>] [<index>] - tail stack events or nodes deploy log
    cmd <cell-name> <role> <index> - run command on node n
    proxy <cell-name> <role> - open SOCKS proxy to first node in <role>

Arguments:
    <cell-name> - the cell name
    <role> - the role the command refers to. One of nucleus, stateless-body, stateful-body, membrane
    <index> - the index of a node in a certain role, 1-indexed.

Environment variables:

  AWS_KEY_PAIR - EC2 ssh keypair to use (new keypair is created otherwise)
  CELL_BUCKET - S3 bucket used  (new bucket is created otherwise)
  KEYPATH - the local path where <keypair>.pem is found (defaults to
    ${HOME}/.ssh). The .pem extension is required.
  PROXY_PORT - the SOCKS5 proxy port (defaults to ${PROXY_PORT})

All AWS CLI environment variables (e.g. AWS_DEFAULT_REGION, AWS_ACCESS_KEY_ID,
AWS_SECRET_ACCESS_KEY, etc.) and configs apply.

This CLI is a convenience tool, not intended as an exhaustive cluster manager.
For advanced use-cases please use the AWS CLI or the AWS web console.

For additional help use dl-metal-cell-users@adobe.com.
For development related questions use dl-metal-cell-dev@adobe.com
Github git.corp.adobe.com/metal-cell/cell-os
Slack https://adobe.slack.com/messages/metal-cell/

EOD
}

ROLES="nucleus, stateless-body, stateful-body, membrane"

parse_args() {
  [[ ! -z $1 ]] && action=$1
  [[ ! -z $2 ]] && cell_name=$2
  [[ ! -z $2 ]] && template_url=$2
  [[ ! -z $3 ]] && role=$3
  [[ ! -z $4 ]] && index=$4
  [[ ! -z $4 ]] && capacity=$4
  full_cell_name="cell-os--${cell_name}"
  bucket_name="${CELL_BUCKET:-${full_cell_name}}"
  aws_key_pair="${AWS_KEY_PAIR:-${full_cell_name}}"
  key_file=${KEYPATH:-"${HOME}/.ssh"}/${aws_key_pair}.pem

  stack_name="${cell_name}" # TODO stack name should read selected region
}

check_cell_name() {
  if [[ -z "${cell_name}" ]]; then
    echo "error: cell_name can't be empty"
    VALIDATION_ERROR=true
    return 1
  fi
  return 0
}

create_key() {
  if [[ -z "${AWS_KEY_PAIR}" ]]; then
    echo "creating keypair ${aws_key_pair}"
    ret=$(aws $AWS_OPTIONS ec2 describe-key-pairs \
      --filters Name=key-name,Values="${aws_key_pair}" \
      --query "KeyPairs[*][KeyName]")
    if  [[ ! -z "${ret}" || -e "${key_file}" ]]; then
      printf "Keypair conflict. Trying to create ${aws_key_pair} in \n\
        ${key_file}, but it already exists. Please delete it, try another \n\
        cell name or use this key instead by setting it through AWS_KEY_PAIR.\n"
      return 1
    fi
    ret=$(aws ec2 create-key-pair --key-name "${aws_key_pair}" --output json) || return 1
    key=$(echo "${ret}" | sed -n 2p | cut -d'"' -f 4)
    echo -e "${key}" > ${key_file}
    chmod 600 ${key_file}
  fi
}

delete_key() {
  if [[ -z "${AWS_KEY_PAIR}" ]]; then
    echo "deleting keypair ${aws_key_pair}"
    ret=$(aws ec2 delete-key-pair --key-name "${aws_key_pair}")
    rm -f "${key_file}"
  fi
}

check_role() {
  if ! [[ "${role}" == "nucleus" || "${role}" == "stateless-body" \
    || "${role}" == "stateful-body" || "${role}" == "membrane"  ]]; then
    echo "please provide role (${ROLES})" >&2
    exit 1
  fi
}

cfn() {
  TAGS="--tags Key=name,Value=\"${cell_name}\" Key=version,Value=\"${VERSION}\""
  if [[ "${1}" = "update" ]]
  then
    TAGS=""
  fi

  aws cloudformation ${1}-stack \
      --template-url "https://s3.amazonaws.com/${bucket_name}/${full_cell_name}/$(basename ${base_stack})" \
      --stack-name "${stack_name}" \
      ${TAGS} \
      --capabilities CAPABILITY_IAM \
      --parameters \
          ${extra_parameters} \
          ParameterKey=CellName,ParameterValue="${cell_name}" \
          ParameterKey=CellOsVersionBundle,ParameterValue="cell-os-base-${VERSION}" \
          ParameterKey=KeyName,ParameterValue="${aws_key_pair}" \
          ParameterKey=BucketName,ParameterValue="${bucket_name}" \
          ParameterKey=SaasBaseAccessKeyId,ParameterValue="${SAASBASE_ACCESS_KEY_ID}" \
          ParameterKey=SaasBaseSecretAccessKey,ParameterValue="${SAASBASE_SECRET_ACCESS_KEY}" \
  || { exit 1; }
}

build_stack_files() {
  echo "creating stacks"
  rm -rf "${DIR}/deploy/aws/build"
  mkdir "${DIR}/deploy/aws/build"
  python "${DIR}/deploy/aws/elastic-cell.py" "${1}" > "${DIR}/deploy/aws/build/elastic-cell.json"
  python "${DIR}/deploy/aws/elastic-cell-scaling-group.py" > "${DIR}/deploy/aws/build/elastic-cell-scaling-group.json"
  base_stack="${DIR}/deploy/aws/build/elastic-cell.json"
  sub_stack="${DIR}/deploy/aws/build/elastic-cell-scaling-group.json"
}

create_bucket() {
  if [[ -z "${CELL_BUCKET}" ]]; then
    echo "creating s3 bucket s3://${bucket_name}"
    ret=$(aws s3 mb "s3://${bucket_name}") || return 1
  fi
}

delete_bucket() {
  if [[ -z "${CELL_BUCKET}" ]]; then
    aws s3 rm --recursive --include "*" s3://${bucket_name}
    aws s3 rb s3://${bucket_name}
  else
    aws s3 rm --recursive --include "*" s3://${bucket_name}/${full_cell_name}/
  fi
}

copy_to_bucket() {
  echo "copy stack to s3://${bucket_name}"
  ret=$(aws s3 cp ${base_stack} "s3://${bucket_name}/${full_cell_name}/")
  ret=$(aws s3 cp ${sub_stack} "s3://${bucket_name}/${full_cell_name}/")
  if [[ ! $? -eq 0 ]]; then
    exit 1
  fi
}

read -r -d '' FOOTER << EOM
To watch your cell infrastructure provisioning log you can
      ./cell log ${cell_name}
For detailed node provisioning logs
      ./cell log ${cell_name} nucleus 1
\n
EOM

update() {
  [[ check_cell_name ]] || return 1

  build_stack_files
  copy_to_bucket

  echo "updating stack ${stack_name}..."
  cfn update
  printf "${CONFIG}"
  printf "${FOOTER}"
  exit 0
}

create() {
  [[ check_cell_name ]] || return 1

  create_bucket || return 1
  create_key || {
    delete_bucket
    return 1
  }
  build_stack_files || {
    delete_bucket
    delete_key
    return 1
  }
  copy_to_bucket
  seed

  echo "creating stack ${stack_name}..."
  cfn create || {
    delete_bucket
    delete_key
    return 1
  }
  printf "${CONFIG}"
  printf "${FOOTER}"
  exit 0
}

delete() {
  [[ check_cell_name ]] || return 1
  echo "WARNING: THIS WILL DELETE ALL RESOURCES ASSOCIATED TO ${cell_name}"
  echo "DELETE s3://${bucket_name}/${full_cell_name}"
  aws s3 ls --summarize s3://${bucket_name}/${full_cell_name}
  echo "DELETE ${key_file}"
  echo "DELETE ${aws_key_pair} from current region"
  echo "DELETE CF stack ${stack_name}"
  echo "--------------------------------------------------------------------"
  echo "for verification please type the name of the cell you want to delete"
  read cell_to_delete
  if [[ "${cell_to_delete}" != "${cell_name}" ]]; then
    echo "cell name doesn't match cell to delete" #1>&2
    exit 1
  fi
  aws cloudformation delete-stack --stack-name ${stack_name}
  delete_bucket
  delete_key
  exit 0
}

cfn_elb() {
  format=${1:-"LoadBalancerName, DNSName"}
  aws ${AWS_OPTIONS} elb describe-load-balancers \
    --query "LoadBalancerDescriptions[*].[$format]" \
    --output ${2:-text} \
    | grep "${cell_name}"
}

cfn_instances() {
  format=${2:-"PublicIpAddress, PrivateIpAddress, ImageId, State.Name, KeyName"}
  aws ${AWS_OPTIONS} ec2 describe-instances \
    --query "Reservations[*].Instances[*].[$format]" \
    --filters \
    Name=tag:cell,Values=$cell_name \
    Name=instance-state-name,Values=*ing \
    Name=tag:role,Values=$1 \
    --output ${3:-text}
}

list() {
  if [[ -z "${cell_name}" ]]; then
    aws cloudformation describe-stacks  --query "Stacks[? (Tags[? Key=='name']\
      && Tags[?Key=='version'] )][StackName, StackStatus, Tags[? Key=='version']\
      .Value | [0], CreationTime]" --output table \
      | grep -Ev '(NucleusStack|MembraneStack|BodyStack)'
  else
    echo "[load balancers]"
    cfn_elb "" text
    echo "[nucleus]"
    cfn_instances nucleus
    echo "[stateless-body]"
    cfn_instances stateless-body
    echo "[stateful-body]"
    cfn_instances stateful-body
    echo "[membrane]"
    cfn_instances membrane
  fi
  exit 0
}

scale() {
  check_role
  if ! [[ ${capacity} -eq ${capacity} ]]; then
    echo capacity must be an integer >&2
    exit 1
  fi
  # jmespath outputs some trash which we need to filter out
  scaling_group=$(aws autoscaling describe-auto-scaling-groups --output text \
    --query "AutoScalingGroups[? (Tags[? Key=='role' && Value=='${role}'] \
    && Tags[?Key=='cell' && Value=='${cell_name}'])]\
    .AutoScalingGroupName")
  echo "Scaling ${cell_name}.${role}(${scaling_group}) to ${capacity}"
  result=$(aws autoscaling update-auto-scaling-group --auto-scaling-group-name \
    ${scaling_group} --desired-capacity ${capacity})
  echo "${result}"
exit
}

cell_ssh() {
  check_role

  ssh_options="${1} -o ConnectTimeout=${SSH_TIMEOUT}"
  if [[ -z "${index}" || -n "${index//[0-9]/}" ]]; then
    index=1
  fi
  ip=$(aws ${AWS_OPTIONS} ec2 describe-instances \
    --query 'Reservations[*].Instances[*].[PublicIpAddress]' \
    --filters Name=instance-state-code,Values=16 \
    Name=tag:cell,Values=${cell_name} Name=tag:role,Values=${role} \
    | sed -n "${index} p")
  if [[ "${ip}" == "None" || -z "${ip}" ]]; then
    echo "can't find node ${index} in ${role} yet. Is the cell fully up?"
    exit 1
  fi
  ip=$( echo "${ip}" | cut -d$'\t' -f1 )
  printf "ip=${ip} \ncommand=${2:-}\n"
  if ! [[ -e "${key_file}" ]]; then
    echo "can't find ${key_file}. Set your KEYPATH env var to the \
      ${aws_key_pair}.pem location"
    exit 1
  fi
  ssh ${ssh_options} "${SSH_USER}@${ip}" -i "${key_file}" "${2:-}"
}

log() {
  [[ check_cell_name ]] || return 1
  if [[ -z "${role}" ]]; then
    watch -n 1 "aws cloudformation describe-stack-events \
      --stack-name ${stack_name} --output table \
      --query 'StackEvents[*].[Timestamp, LogicalResourceId, ResourceStatus]' \
      --max-items 10"
    exit 0
  else
    check_role
    command="tail -f /var/log/cloud-init-output.log"

    cell_ssh "" "${command}"
  fi
}

cmd() {
  if [[ -z "${5}" ]]; then
    echo "command can't be empty"
    printf "${USAGE}"
    exit 1
  fi
  cell_ssh "-t" "${5}"
}

proxy() {
  pgrep -f -- "-N -g -C -D ${PROXY_PORT}" | xargs kill -9
  cell_ssh "-N -g -C -D ${PROXY_PORT}" ""
}

build_seed() {
  [[ check_cell_name ]] || return 1
  pushd "${DIR}/deploy/"
  tar zcf seed.tar.gz seed
}

seed() {
  build_seed
  aws s3 cp seed.tar.gz s3://${bucket_name}/${full_cell_name}/shared/cell-os/
  popd &>/dev/null
  aws s3 cp "${DIR}/cell-os-base.yaml" "s3://${bucket_name}/${full_cell_name}/shared/cell-os/cell-os-base-${VERSION}.yaml"
}

cell_i2cssh() {
  ssh_options="-o ConnectTimeout=${SSH_TIMEOUT}"
  rolestmp=${role:-${ROLES//, / }}
  roles=($(echo ${rolestmp}))
  machines=$(for role in "${roles[@]}"; do
    aws ${AWS_OPTIONS} ec2 describe-instances \
      --query 'Reservations[*].Instances[*].[PublicIpAddress]' \
      --filters Name=instance-state-code,Values=16 \
      Name=tag:cell,Values=${cell_name} Name=tag:role,Values=${role}
  done | sed 's/$/,/g' | tr -d "\n" | sed 's/,$//g')

  if ! [[ -e "${key_file}" ]]; then
    echo "can't find ${key_file}. Set your KEYPATH env var to the .pem location"
    exit 1
  fi
  i2cssh -l ${SSH_USER} -m $machines -Xi="${key_file}"
}

parse_args "${@}"

read -r -d '' CONFIG << EOM
  aws_key_pair  = "${aws_key_pair}" - created with cell if not specified
  BUCKET_NAME   = "${bucket_name}" (readonly - cell-os--<cell-name>)
  STACK_NAME    = "${stack_name}" (readonly - <cell-name>)
  \n
EOM

# action
case "${1}" in
  build)
    build_stack_files "${template_url:? please provide the full template URL}"
    build_seed
    ;;
  create)
    create
    ;;
  update)
    update
    ;;
  delete)
    delete
    ;;
  list)
    list
    ;;
  scale)
    scale
    ;;
  i2cssh)
    cell_i2cssh
    ;;
  ssh)
    cell_ssh
    ;;
  log)
    log
    ;;
  cmd)
    cmd "${@}"
    ;;
  seed)
    seed
    ;;
  proxy)
    proxy
    ;;
  help)
    usage
    exit 0
    ;;
  *)
  echo "error: invalid action ${1}"
  VALIDATION_ERROR=true
esac

if [[ "${VALIDATION_ERROR}" == true ]]; then
  printf "${CONFIG}"
  exit 1
fi
