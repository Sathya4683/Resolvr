output "public_ip" {
  value = aws_eip.resolvr.public_ip
}

output "region" {
  value = var.region
}

output "instance_id" {
  value = aws_instance.resolvr.id
}

#sslip.io turns 1-2-3-4.sslip.io into 1.2.3.4, a free hostname so caddy can get an https cert
output "app_host" {
  value = "${replace(aws_eip.resolvr.public_ip, ".", "-")}.sslip.io"
}
