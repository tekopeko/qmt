output "instance_public_ip" {
  description = "The reserved IPv4: the Cloudflare A records of both domains point here."
  value       = scaleway_instance_ip.webhost.address
}

output "ssh_command" {
  value = "ssh root@${scaleway_instance_ip.webhost.address}"
}
