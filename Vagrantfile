# -*- mode: ruby -*-
# vi: set ft=ruby :


require 'vagrant-aws'
Vagrant.configure('2') do |config|
  config.vm.box = 'dummy'
  config.vm.synced_folder ".", "/vagrant", disabled: true

  config.vm.provider 'aws' do |aws, override|
    aws.keypair_name = 'lucidum-us-east-1'
    aws.instance_type = 't3.large'
    aws.region = 'us-east-1'
    aws.associate_public_ip = true
    aws.subnet_id = 'subnet-98a07896'
    aws.ami = 'ami-0817d428a6fb68645'
    aws.security_groups = [ 'sg-0e398bdf2b70c0895' ]
    aws.block_device_mapping = [{ 'DeviceName' => '/dev/sda1', 'Ebs.VolumeSize' => 100 }]
    aws.iam_instance_profile_name = "vagrant_development"
    aws.tags = { 'Name' => 'vagrant update-manager development' }
    override.ssh.username = 'ubuntu'
    override.ssh.private_key_path = '~/.ssh/lucidum-us-east-1.pem'
  end

  config.vm.provision "shell",
    env: {
      "AWS_REGION" => "us-west-1",
      "DYNACONF_jinja_templates_dir" => "tmplts",
      "DYNACONF_ecr_base" => "308025194586.dkr.ecr.us-west-1.amazonaws.com",
      "DYNACONF_lucidum_dir" => "/usr/lucidum"
    },
    inline: <<-SCRIPT
      set -o errexit
      set -o errtrace
      set -o functrace
      set -o hashall
      set -o pipefail
      set -o verbose
      set -o xtrace
      set -o physical
      set -o privileged
      set -o nounset
      set -o noclobber

      env | sort | nl
      sudo apt-get update -y
      sleep 5
      sudo apt-get install python3-venv docker.io -y
      rm -rf lucidum_venv
      python3 -m venv lucidum_venv
      source lucidum_venv/bin/activate
      rm -rf update-manager
      git clone https://github.com/LucidumInc/update-manager.git
      cd update-manager
      pip3 install --no-cache-dir -r requirements.txt
      aws sts get-caller-identity
      python3 update_manager.py --help
SCRIPT

end
