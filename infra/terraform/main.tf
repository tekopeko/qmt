# One box for both web apps: QMT (qmt.mojimakrosi.com) and mojimakrosi
# (mojimakrosi.com). Provisioned the way the trader dashboard is
# (trader/infra/main.tf), never on the trader's box.

resource "scaleway_iam_ssh_key" "webhost" {
  name       = "webhost"
  public_key = trimspace(file(pathexpand(var.ssh_public_key_path)))
}

resource "scaleway_instance_ip" "webhost" {
  # Reserved: survives a stop/start, so the Cloudflare A records are set once.
  lifecycle {
    prevent_destroy = true # replacing it must be a deliberate edit here, never a plan side effect
  }
}

resource "scaleway_instance_security_group" "webhost" {
  name                    = "webhost-sg"
  inbound_default_policy  = "drop"
  outbound_default_policy = "accept"

  inbound_rule {
    action   = "accept"
    port     = 22
    ip_range = "0.0.0.0/0"
  }
  inbound_rule {
    action = "accept"
    port   = 80
  }
  inbound_rule {
    action = "accept"
    port   = 443
  }
  # Everything else inbound is dropped (inbound_default_policy). ufw does the
  # same on the host (cloud-init): the perimeter here, the host there.
}

resource "scaleway_instance_server" "webhost" {
  name  = "webhost"
  type  = var.instance_type
  image = "ubuntu_noble" # Ubuntu 24.04, the label the trader's box uses

  tags = ["webhost"]

  ip_id             = scaleway_instance_ip.webhost.id
  security_group_id = scaleway_instance_security_group.webhost.id

  root_volume {
    size_in_gb = 20
  }

  # First-boot bootstrap (Docker, Caddy, ufw, unattended-upgrades, the backup
  # and autoheal crons, awscli): cloud-init.yaml.tftpl. cloud-init runs it
  # once; editing it later updates the instance's metadata, not the box.
  user_data = {
    cloud-init = templatefile("${path.module}/cloud-init.yaml.tftpl", {
      qmt_domain = var.qmt_domain
      mm_domain  = var.mm_domain
    })
  }

  # Scaleway injects every SSH key registered in the project at first boot;
  # this only makes sure ours exists before the server does.
  depends_on = [scaleway_iam_ssh_key.webhost]

  lifecycle {
    # Both databases live on this box's disk (the pgdata volume): a plan that
    # would replace it must first be a deliberate edit of this block.
    prevent_destroy = true
  }
}
