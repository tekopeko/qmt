terraform {
  # The trader's floor: >= 1.10 is what the S3 backend's `use_lockfile`
  # needs, should this state move there later (below).
  required_version = ">= 1.10"
  required_providers {
    scaleway = {
      source  = "scaleway/scaleway"
      version = "~> 2.0"
    }
  }

  # State is LOCAL: terraform.tfstate in this directory, gitignored (see
  # .gitignore here). It holds no secret, but it is the only record of what
  # exists: keep it, and keep a copy off the laptop.
  #
  # Moving it to Object Storage later, the way the trader did
  # (trader/infra/versions.tf):
  #   1. add a bucket for it to storage.tf (e.g. "teko-webhost-tfstate") and
  #      `terraform apply` while the state is still local, which creates it;
  #   2. add the block below and run `terraform init -migrate-state`.
  #
  #   backend "s3" {
  #     bucket                      = "teko-webhost-tfstate"
  #     key                         = "webhost.tfstate"
  #     region                      = "fr-par"
  #     endpoints                   = { s3 = "https://s3.fr-par.scw.cloud" }
  #     use_path_style              = true
  #     skip_credentials_validation = true
  #     skip_region_validation      = true
  #     skip_requesting_account_id  = true
  #     use_lockfile                = true
  #   }
  #
  # The backend reads AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY, set to the
  # SCW_ACCESS_KEY / SCW_SECRET_KEY values; that key needs
  # ObjectStorageFullAccess (bucket rights alone 403 every object call).
}

# Credentials come from the environment, never from a file in this repo:
#   SCW_ACCESS_KEY, SCW_SECRET_KEY, SCW_DEFAULT_PROJECT_ID
# (see ../README.md). DNS is manual at Cloudflare: no DNS provider here.
provider "scaleway" {
  zone   = "fr-par-1"
  region = "fr-par"
}
