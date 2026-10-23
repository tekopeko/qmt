# Off-site copies of the nightly database dumps: ../backup.sh uploads each
# night's when /opt/backups/s3.env exists on the box. Private (the default
# ACL). The lifecycle rule expires objects after 30 days, so no rotation
# logic lives in the script: the trader's backups bucket, for this box.
resource "scaleway_object_bucket" "backups" {
  name   = "teko-webhost-backups"
  region = "fr-par"

  tags = {
    purpose = "nightly-offsite-backups"
  }

  lifecycle_rule {
    id      = "expire-old-backups"
    enabled = true
    expiration {
      days = 30
    }
  }
}
