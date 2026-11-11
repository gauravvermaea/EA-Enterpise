# EA Explorer's deployer (phase 36, D555): the tools eax deploy needs to set up another place from System admin >
# Deploy: ssh and scp, curl, git, and the AWS, Azure and DigitalOcean command-line tools. Built by the operations
# helper the first time a deployment runs (eaexplorer/deployer:<version>); each deployment runs in a short-lived
# container of it with only its run folder and this release's eaxcli and templates mounted (services/ops/deploys.py).
FROM python:3.12-slim
ARG DOCTL_VERSION=1.115.0
RUN apt-get update \
 && apt-get install -y --no-install-recommends openssh-client curl git ca-certificates unzip gnupg lsb-release \
 && curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-$(uname -m).zip" -o /tmp/awscli.zip \
 && unzip -q /tmp/awscli.zip -d /tmp && /tmp/aws/install && rm -rf /tmp/aws /tmp/awscli.zip \
 && curl -fsSL https://aka.ms/InstallAzureCLIDeb | bash \
 && arch="$(dpkg --print-architecture)" \
 && curl -fsSL "https://github.com/digitalocean/doctl/releases/download/v${DOCTL_VERSION}/doctl-${DOCTL_VERSION}-linux-${arch}.tar.gz" \
    | tar -xz -C /usr/local/bin doctl \
 && apt-get purge -y unzip gnupg lsb-release && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*
WORKDIR /eax
CMD ["python", "-m", "eaxcli.deploy_runner", "/run"]
