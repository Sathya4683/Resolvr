variable "region" {
  default = "ap-south-1"
}

#8 vcpu / 16gb, the embedding + reranker models run on cpu so cores matter
variable "instance_type" {
  default = "c7i.2xlarge"
}

variable "disk_gb" {
  default = 40
}

variable "ssh_public_key" {
  default = "~/.ssh/id_ed25519.pub"
}
