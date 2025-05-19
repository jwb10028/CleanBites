#!/bin/bash
#mirror any changes here on travisdeploy.sh
# Define variables
AWS_REGION="us-west-2"
ECR_REPO="730335518224.dkr.ecr.$AWS_REGION.amazonaws.com/cleanbites"
EB_ENV="CleanBites-amznlnx-docker-stable-env"

echo "🚀 Building Docker image..."
docker build -t cleanbites .

echo "🔑 Authenticating AWS ECR..."
aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin $ECR_REPO

echo "🏷️ Tagging image..."
docker tag cleanbites:latest $ECR_REPO:latest

echo "📤 Pushing image to AWS ECR..."
docker push $ECR_REPO:latest

echo "🔧 Running cleanup commands on instance..."
powershell.exe -Command "eb ssh $EB_ENV --command 'sudo docker rm -f \$(sudo docker ps -aq); sudo docker system prune -a -f'"

echo "📦 Deploying to Elastic Beanstalk..."
powershell.exe -Command "eb deploy $EB_ENV"

echo "✅ Deployment completed!"