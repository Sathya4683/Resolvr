variable "region" {
  default = "ap-south-1"
}

#2 vcpu / 8gb, the biggest type the aws free plan (credits) allows
#on a paid account c7i.2xlarge (8 vcpu) makes the models a lot snappier
variable "instance_type" {
  default = "m7i-flex.large"
}

variable "disk_gb" {
  default = 40
}

variable "ssh_public_key" {
  default = "~/.ssh/id_ed25519.pub"
}
