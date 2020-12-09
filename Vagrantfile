# -*- mode: ruby -*-
# vi: set ft=ruby :


require 'vagrant-aws'
Vagrant.configure('2') do |config|
  config.vm.box = 'dummy'

  config.vm.provider 'aws' do |aws, override|
    aws.keypair_name = 'lucidum-us-east-1'
    aws.instance_type = 't3.large'
    aws.region = 'us-east-1'
    aws.associate_public_ip = true
    aws.subnet_id = 'subnet-98a07896'
    aws.ami = 'ami-0817d428a6fb68645'
    aws.security_groups = [ 'sg-0e398bdf2b70c0895' ]
    aws.block_device_mapping = [{ 'DeviceName' => '/dev/sda1', 'Ebs.VolumeSize' => 100 }]
    aws.iam_instance_profile_name = "vagrant_development_update_manager"
    aws.tags = { 'Name' => 'vagrant update-manager development' }
    override.ssh.username = 'ubuntu'
    override.ssh.private_key_path = '~/.ssh/lucidum-us-east-1.pem'
  end

  config.vm.provision "shell", env: {"AWS_REGION" => "us-west-1"}, inline: <<-SCRIPT
    sudo apt update -y
    sudo apt install python3-venv -y
    python3 -m venv lucidum_venv
    source lucidum_venv/bin/activate
    git clone https://github.com/LucidumInc/update-manager.git
    cd update-manager
    pip3 install --no-cache-dir -r requirements.txt
    aws sts get-caller-identity
    python3 update_manager.py help
SCRIPT

end
