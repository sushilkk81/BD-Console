resource "aws_ecr_repository" "backend" {
  name = "${var.project}-backend"
}

resource "aws_ecr_repository" "frontend" {
  name = "${var.project}-frontend"
}
