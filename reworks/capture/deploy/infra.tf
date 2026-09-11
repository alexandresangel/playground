# Capture ACA and its identity grants only. Existing storage/container ownership stays with Pascal.
# The company aca_app module and environment storage helper are unchanged.

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

variable "resource_group_name" {
  type = string
}

variable "env_name" {
  type = string
}

variable "storage_account_name" {
  type = string
}

variable "registry_server" {
  type = string
}

variable "registry_username" {
  type = string
}

variable "registry_password" {
  type      = string
  sensitive = true
}

variable "chat_blob_container" {
  type    = string
  default = "chat-sessions"
}

# Agent config (system_prompt.md, skills/*/catalog.json + prompts).
variable "config_blob_container" {
  type    = string
  default = "agent-config"
}

# Capture has separate state and reuses the existing containers.
variable "app_name" {
  type    = string
  default = "capture"
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

data "azurerm_storage_container" "chat" {
  name                  = var.chat_blob_container
  storage_account_id    = data.azurerm_storage_account.env.id
}

data "azurerm_storage_container" "config" {
  name                  = var.config_blob_container
  storage_account_id    = data.azurerm_storage_account.env.id
}

module "app" {
  source = "./.terraform-modules/aca_app"

  name                         = var.app_name
  resource_group_name          = data.azurerm_resource_group.rg.name
  container_app_environment_id = data.azurerm_container_app_environment.env.id
  environment_default_domain   = data.azurerm_container_app_environment.env.default_domain
  target_port                  = 8000
  registry_server              = var.registry_server
  registry_username            = var.registry_username
  registry_password            = var.registry_password
  secret_names                 = ["chat-config", "jwt-keystore-p12-b64"]
  env_plain                    = { PORT = "8000" }
  env_secrets                  = {
    CHAT_CONFIG           = "chat-config"
    JWT_KEYSTORE_P12_B64  = "jwt-keystore-p12-b64"
  }
  public_url_env_name          = "AGENT_URL"
  system_assigned_identity     = true
}

locals {
  chat_blob_scope   = "${data.azurerm_storage_account.env.id}/blobServices/default/containers/${var.chat_blob_container}"
  config_blob_scope = "${data.azurerm_storage_account.env.id}/blobServices/default/containers/${var.config_blob_container}"
}

resource "azurerm_role_assignment" "chat_blob" {
  scope                = local.chat_blob_scope
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = module.app.principal_id
  principal_type       = "ServicePrincipal"
  depends_on           = [data.azurerm_storage_container.chat, module.app]
}

resource "azurerm_role_assignment" "config_blob" {
  scope                = local.config_blob_scope
  role_definition_name = "Storage Blob Data Reader"
  principal_id         = module.app.principal_id
  principal_type       = "ServicePrincipal"
  depends_on           = [data.azurerm_storage_container.config, module.app]
}

