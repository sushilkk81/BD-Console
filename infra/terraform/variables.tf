variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "project" {
  type    = string
  default = "bdconsole"
}

variable "db_password" {
  type      = string
  sensitive = true
}

variable "jwt_secret" {
  type      = string
  sensitive = true
}
