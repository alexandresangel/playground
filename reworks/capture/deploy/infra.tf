terraform {
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
  }
  backend "azurerm" {}
}

provider "azurerm" {
  features {}
}

variable "resource_group_name" { type = string }
variable "env_name" { type = string }
variable "storage_account_name" { type = string }
variable "registry_server" { type = string }
variable "registry_username" { type = string }
variable "registry_password" {
  type      = string
  sensitive = true
}
variable "config_blob_container" {
  type    = string
  default = "agent-config"
}

data "azurerm_resource_group" "rg" {
  name = var.resource_group_name
}

data "azurerm_container_app_environment" "env" {
  name                = var.env_name
  resource_group_name = data.azurerm_resource_group.rg.name
}

data "azurerm_storage_account" "env" {
  name                = var.storage_account_name
  resource_group_name = data.azurerm_resource_group.rg.name
}

# This is the same shared ACA module/deployment contract used by diapason-agent and diapason-mcp.
# deploy_init materializes deploy/.terraform-modules/aca_app before terraform runs.
module "app" {
  source = "./.terraform-modules/aca_app"

  name                         = "capture"
  resource_group_name          = data.azurerm_resource_group.rg.name
  container_app_environment_id = data.azurerm_container_app_environment.env.id
  environment_default_domain   = data.azurerm_container_app_environment.env.default_domain
  target_port                  = 8000
  registry_server              = var.registry_server
  registry_username            = var.registry_username
  registry_password            = var.registry_password
  secret_names                 = ["capture-config", "jwt-keystore-p12-b64"]
  env_plain = {
    PORT              = "8000"
    OTEL_SERVICE_NAME = "capture"
  }
  env_secrets = {
    CAPTURE_CONFIG        = "capture-config"
    JWT_KEYSTORE_P12_B64  = "jwt-keystore-p12-b64"
  }
  public_url_env_name      = "CAPTURE_URL"
  system_assigned_identity = true
}

locals {
  config_blob_scope = "${data.azurerm_storage_account.env.id}/blobServices/default/containers/${var.config_blob_container}"
}

resource "azurerm_role_assignment" "config_blob" {
  scope                = local.config_blob_scope
  role_definition_name = "Storage Blob Data Reader"
  principal_id         = module.app.principal_id
  principal_type       = "ServicePrincipal"
  depends_on           = [module.app]
}

output "capture_principal_id" {
  value = module.app.principal_id
}

