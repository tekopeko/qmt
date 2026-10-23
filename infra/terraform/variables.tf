variable "instance_type" {
  type        = string
  default     = "DEV1-S"
  description = "Scaleway instance type. DEV1-S is 2 vCPU / 2 GB: Postgres, the two apps (capped at 512m and 768m) and Caddy."
}

variable "ssh_public_key_path" {
  type        = string
  default     = "~/.ssh/id_ed25519.pub"
  description = "Local path to the public key that gets root SSH access to the box."
}

variable "qmt_domain" {
  type        = string
  default     = "qmt.mojimakrosi.com"
  description = "QMT's hostname. Caddy proxies it to 127.0.0.1:8001."
}

variable "mm_domain" {
  type        = string
  default     = "mojimakrosi.com"
  description = "mojimakrosi's apex. Caddy proxies it to 127.0.0.1:8002 and redirects www.<it> to it."
}
