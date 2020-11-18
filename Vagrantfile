$addrs = {
  "manager1" => "192.168.50.2", 
  "worker1" => "192.168.50.3",
  "worker2" => "192.168.50.4"
}

$prov_base = <<-SCRIPT
/vagrant/scripts/install-deps.sh
/vagrant/scripts/install-docker.sh
curl -s https://gist.githubusercontent.com/agmangas/3f8e58655829c229d5bb986a2911a9d8/raw | bash
/vagrant/scripts/build-image.sh
/vagrant/scripts/install-pumba.sh
SCRIPT

$prov_env = <<-SCRIPT
tee "/etc/profile.d/custom.sh" <<EOF
export IP_MANAGER1=#{$addrs["manager1"]}
export IP_WORKER1=#{$addrs["worker1"]}
export IP_WORKER2=#{$addrs["worker2"]}
EOF
SCRIPT

$prov_swarm_init = <<-SCRIPT
docker swarm init --advertise-addr #{$addrs["manager1"]}
SCRIPT

Vagrant.configure("2") do |config|
  config.vm.box = "bento/ubuntu-18.04"

  config.vm.provider "virtualbox" do |v|
    v.memory = 4096
    v.cpus = 2
  end

  config.vm.provision "shell", inline: $prov_env, run: "always"
  config.vm.provision "shell", inline: $prov_base

  config.vm.define "manager1", primary: true do |c|
    c.vm.hostname = "manager1"
    c.vm.network "private_network", ip: $addrs["manager1"]
    c.vm.provision "shell", inline: $prov_swarm_init
  end

  config.vm.define "worker1" do |c|
    c.vm.hostname = "worker1"
    c.vm.network "private_network", ip: $addrs["worker1"]
  end

  config.vm.define "worker2" do |c|
    c.vm.hostname = "worker2"
    c.vm.network "private_network", ip: $addrs["worker2"]
  end
end