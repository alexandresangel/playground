# Capture app shell. Shared deployment tooling manages Terraform state.

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

data "azurerm_resource_group" "rg" {
  name = var.resource_group_name
}

data "azurerm_container_app_environment" "env" {
  name                = var.env_name
  resource_group_name = data.azurerm_resource_group.rg.name
}

module "app" {
  source = "./.terraform-modules/aca_app"

  name                         = "diapason-agent"
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
}
