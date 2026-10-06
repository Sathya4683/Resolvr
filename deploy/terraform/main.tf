#one ec2 box that runs the whole docker compose stack, same as on the laptop
terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

provider "aws" {
  region = var.region
}

#latest ubuntu 24.04 from canonical
data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"]

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-*"]
  }
}

resource "aws_key_pair" "me" {
  key_name   = "resolvr-key"
  public_key = file(pathexpand(var.ssh_public_key))
}

#wide open on purpose, the box only runs while i'm demoing it
resource "aws_security_group" "resolvr" {
  name        = "resolvr-sg"
  description = "resolvr demo server"

  ingress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_instance" "resolvr" {
  ami                    = data.aws_ami.ubuntu.id
  instance_type          = var.instance_type
  key_name               = aws_key_pair.me.key_name
  vpc_security_group_ids = [aws_security_group.resolvr.id]

  root_block_device {
    volume_size = var.disk_gb
    volume_type = "gp3"
  }

  #first boot: some swap for the image builds, then docker (the compose plugin comes with it)
  user_data = <<-EOF
    #!/bin/bash
    fallocate -l 4G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
    echo '/swapfile none swap sw 0 0' >> /etc/fstab
    curl -fsSL https://get.docker.com | sh
    usermod -aG docker ubuntu
    systemctl enable --now docker
  EOF

  tags = {
    Name = "resolvr"
  }
}

#fixed ip so the url (and the https cert) stays the same after stop / start
resource "aws_eip" "resolvr" {
  instance = aws_instance.resolvr.id
  domain   = "vpc"
}
