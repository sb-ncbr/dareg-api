# Setup Workflows
This guideline contains all the steps necessary for setting up the workflows platform for the DAREG application. It spans multiple areas, starting from infrastructure deployment and finishing with running a simple workflow through the admin UI of DAREG.

## Setup infrastructure
Infrastructure spans two main areas: first is to deploy a Kubernetes cluster where jobs will run, and second is to deploy Onedata OpenFaaS software there.


### Setup kubernetes cluster
Let's set up a cluster where the workflow and OpenFaaS will be running. In our case, we are managing Kubernetes on our own on OpenStack virtual machines—this will eventually be migrated to managed Kubernetes (Rancher).

1. Set up a project for yourself in OpenStack to have enough quota for creating virtual machines—4 machines (2 for Kubernetes CP and 2 for workers) should be enough.
2. Utilize the Open OnDemand internal tool https://ondemand-dev.metacentrum.cz/pun/sys/dashboard to deploy kubernetes do previously created project
    - Open the Interactive Apps tab and select the option "Kubernetes infra example OS" 
        - <img src="./docs/images/kubernetesInfraExampleOs.png" alt="alt text" width="400" height="400"/>
    - Select a project to use (from step 1), put your SSH public key, and specify the number of nodes for CP and DP.
    - Click launch
    - After  few minutes(30), an interactive session is created for you and the nodes(CP, DP and Bastion) are provisioned
        - <img src="./docs/images/kubernetesInfraExampleOSSession.png" alt="alt text" width="400" height="400"/>
3. Assign a public IP to the Bastion server (for deploying Onedata OpenFaaS via Helm charts) and for workers (so that the Onedata provider has access to OpenFaaS). Please note all VMs live within the same network.
4. Configure network security rules for the nodes to make communication between them possible and between onedata provider and openfaas running inside kubernetes
    - CP -> Network security group with following rules
        - ```ALLOW IPv4 icmp from 0.0.0.0/0
            ALLOW IPv4 22/tcp from <network-cidr-of-all-nodes>
            ALLOW IPv4 tcp to 0.0.0.0/0
            ALLOW IPv4 udp from <network-cidr-of-all-nodes>
            ALLOW IPv4 udp to 0.0.0.0/0
            ALLOW IPv4 tcp from <network-cidr-of-all-nodes>
            ALLOW IPv4 6443/tcp from <network-cidr-of-all-nodes>
            ALLOW IPv4 80/tcp from 0.0.0.0/0
            ALLOW IPv4 8080/tcp from 78.128.247.103/32
            ALLOW IPv6 ipv6-icmp to ::/0
            ALLOW IPv4 tcp from 0.0.0.0/0
            ALLOW IPv4 6443/tcp from 0.0.0.0/0
            ALLOW IPv4 icmp to 0.0.0.0/0
            ALLOW IPv4 22/tcp from 0.0.0.0/0
            ALLOW IPv4 443/tcp from 0.0.0.0/0
            ALLOW IPv4 30000-32767/tcp from 78.128.247.103/32
            ALLOW IPv6 tcp to ::/0
            ALLOW IPv6 udp to ::/0
            ```
    - workers -> Network security rules
        - ```ALLOW IPv6 tcp to ::/0
            ALLOW IPv4 30000-32767/tcp from <one-provider-cidr>
            ALLOW IPv4 8080/tcp from <one-provider-cidr>
            ALLOW IPv4 6443/tcp from <one-provider-cidr>
            ALLOW IPv4 tcp to <one-provider-cidr>
            ALLOW IPv4 443/tcp from <one-provider-cidr>
            ALLOW IPv4 30000-32767/tcp to <one-provider-cidr>
            ALLOW IPv4 80/tcp from <one-provider-cidr>
            ALLOW IPv6 tcp from ::/0
            ALLOW IPv4 icmp from 0.0.0.0/0
            ALLOW IPv4 22/tcp from <network-cidr-of-all-nodes>
            ALLOW IPv4 tcp to 0.0.0.0/0
            ALLOW IPv4 udp from <network-cidr-of-all-nodes>
            ALLOW IPv4 udp to 0.0.0.0/0
            ALLOW IPv4 tcp from <network-cidr-of-all-nodes>
            ALLOW IPv4 6443/tcp from <network-cidr-of-all-nodes>
            ALLOW IPv4 80/tcp from 0.0.0.0/0
            ALLOW IPv4 8080/tcp from 78.128.247.103/32
            ALLOW IPv6 ipv6-icmp to ::/0
            ALLOW IPv4 tcp from 0.0.0.0/0
            ALLOW IPv4 6443/tcp from 0.0.0.0/0
            ALLOW IPv4 icmp to 0.0.0.0/0
            ALLOW IPv4 22/tcp from 0.0.0.0/0
            ALLOW IPv4 443/tcp from 0.0.0.0/0
            ALLOW IPv4 30000-32767/tcp from 78.128.247.103/32
            ALLOW IPv6 tcp to ::/0
            ALLOW IPv6 udp to ::/0
            ```
    - bastion -> network security rules
        - ```ALLOW IPv6 from default
            ALLOW IPv4 from default
            ALLOW IPv4 to 0.0.0.0/0
            ALLOW IPv6 to ::/0
            ALLOW IPv4 22/tcp from 0.0.0.0/0
            ALLOW IPv6 22/tcp from ::/0
            ALLOW IPv6 to ::/0
            ALLOW IPv4 from ssh
            ALLOW IPv4 to 0.0.0.0/0
            ALLOW IPv6 from ssh
            ALLOW IPv4 icmp from 0.0.0.0/0
            ALLOW IPv4 22/tcp from <network-cidr-of-all-nodes>
            ALLOW IPv4 tcp to 0.0.0.0/0
            ALLOW IPv4 udp from <network-cidr-of-all-nodes>
            ALLOW IPv4 udp to 0.0.0.0/0
            ALLOW IPv4 tcp from <network-cidr-of-all-nodes>
            ALLOW IPv4 6443/tcp from <network-cidr-of-all-nodes>
            ALLOW IPv4 80/tcp from 0.0.0.0/0
            ALLOW IPv4 8080/tcp from 78.128.247.103/32
            ALLOW IPv6 ipv6-icmp to ::/0
            ALLOW IPv4 tcp from 0.0.0.0/0
            ALLOW IPv4 6443/tcp from 0.0.0.0/0
            ALLOW IPv4 icmp to 0.0.0.0/0
            ALLOW IPv4 22/tcp from 0.0.0.0/0
            ALLOW IPv4 443/tcp from 0.0.0.0/0
            ALLOW IPv4 30000-32767/tcp from 78.128.247.103/32
            ALLOW IPv6 tcp to ::/0
            ALLOW IPv6 udp to ::/0
            ```

### Openfaas instalation (source https://onedata.org/training/automation.html#5 slide 5-9)
1. Let's access bastion/worker via SSH from your local host
2. From the session information in https://ondemand-dev.metacentrum.cz/pun/sys/dashboard generate a kubeconfig(the info is in your session) on your bastion/worker
3. Check that kubectl works for you and you see nodes and DNS pods(some adjustment may be needed - change the config map of DNS Core to 8.8.8.8 or 1.1.1.1, then restart the deployment)
4. Change to some chosen working directory
5. Run git clone https://github.com/onedata/onedata-deployments.git
6. Change file openfaas/ansible/roles/common/tasks/main.yml to the content below to remove Docker install, Kubernetes install, and cluster setup. Set up just roles for the existing cluster:
    - ``` - name: A become=yes block
            become: yes
            block:
                - name: Install apt-transport-https, ca-certificates and python3-pip
                apt:
                    name: apt-transport-https, ca-certificates, python3-pip
                    state: present
                - name: Ensure permissions for ~/.docker
                file:
                    path: "{{ ansible_user_dir }}/.docker"
                    owner: "{{ ansible_user_id }}"
                    recurse: yes
                    mode: 0700
                - name: Install kubernetes python module
                pip:
                    name: kubernetes
                    state: present
                    extra_args: --break-system-packages
                - name: Install kubectl
                get_url:
                    url: https://dl.k8s.io/release/v1.30.0/bin/linux/amd64/kubectl
                    dest: /usr/local/bin/kubectl
                    mode: 0755

            - name: Check ClusterRoleBinding existence
            shell: kubectl get clusterrolebinding serviceaccounts-cluster-admin -o json
            register: clusterrolebinding_output
            ignore_errors: true

            - name: Print ClusterRoleBinding existence
            debug:
                msg: "ClusterRoleBinding already exists: {{ 'true' if clusterrolebinding_output.rc == 0 else 'false' }}"

            - name: Configure permissions for k8s
            shell: kubectl create clusterrolebinding serviceaccounts-cluster-admin   --clusterrole=cluster-admin   --group=system:serviceaccounts
            when: clusterrolebinding_output.rc
            - name: Download Helm installation script
            get_url:
                url: https://raw.githubusercontent.com/helm/helm/master/scripts/get-helm-3
                dest: /tmp/get_helm.sh
                mode: 0755

            - name: Run Helm installation script
            shell: /tmp/get_helm.sh
            become: yes
            args:
                creates: /usr/local/bin/helm

            - name: Verify Helm installation
            shell: helm version --short
            register: helm_output

            - name: Print Helm version
            debug:
                msg: "Helm version: {{ helm_output.stdout }}"
            ```   
7. Edit ./group_vars/all.yaml with proper values. This section is illustrative, add your own values
    - ```
        # Oneprovider hostname - should be accessible from the OpenFaaS host.
        oneprovider_hostname: oneprovider01.devel.onedata.e-infra.cz    # replace ??? with your Oneprovider subdomain label

        # IP address of the VM where OpenFaaS will be deployed.
        # Should be accessible from the Oneprovider host.
        openfaas_host: 78.128.235.174   # replace ??? with your vm ip - hint: hostname -i; worker public IP

        ...

        # Openfaas admin password
        openfaas_admin_password: <choose-your-password> # will be used later

        ...

        # pod-status-monitor will use this secret to authorize status reports sent to
        # Oneprovider, can be arbitrary.
        openfaas_activity_feed_secret: <choose-your-secret> # will be used later
        ```
8. Edit ./hosts with proper values. This section is illustrative, add your own values
    - ```
        # This is the ansible inventory host file. Replace the IP
        # addresses accordingly.
        #
        # Both hosts specified here must have connectivity to each other:
        #  * Oneprovider contacts OpenFaaS to schedule jobs.
        #  * OpenFaaS contacts the Oneprovider to return job results.
        #  * Auxiliary machinery running on the OpenFaaS host report the activity and status
        #    of the cluster to the Oneprovider.


        [openfaas]
        # The host where openfaas will be deployed
        openfaas-vm ansible_host=78.128.235.174  ansible_connection=local # public worker IP
        [oneprovider]
        # The host where the Oneprovider service is already running
        # (ansible will adjust its configuration and restart it).
        oneprovider-vm ansible_host=147.251.255.78 ansible_user=<your-user-used-in-oneprovider-for-ssh, i.e. debian> # e.g. public IP of the one provider
      ```
9. Improve   to generate a config file for the Oneprovider on the Oneprovider machine
    - ```- name: Obtain openfaas password
            shell: |
                kubectl -n "{{openfaas_namespace}}" get secret openfaas-basic-auth -o jsonpath="{.data.basic-auth-password}" | base64 --decode
            register: kube_output

            - name: Place password in var
            set_fact:
                openfaas_admin_password: "{{kube_output.stdout}}"

            - name: Generate op-openfaas.config
            template:
                src: openfaas-config.j2
                dest: /home/debian/oneprovider_config/99-openfaas.config # this is destination file where oneprovider config will be produced; we will use that later
                ```
10. Add SSH key of your machine (where ansible is located - worker, bastion) to Oneprovider so the Ansible can perform step 9. Make sure Oneprovider is reachable at port 22.
11. Run 
    - ```cd onedata-deployments/openfaas/ansible/
        sudo apt install -y python3 python3-pip
        sudo python3 -m pip install ansible "Jinja2>=2.10,<3.1" jmespath kubernetes
        ```
    - or setup the prerequisities according this readme https://github.com/onedata/onedata-deployments/blob/master/openfaas/ansible/README.md 
12. Make sure all nodes can be connected via SSH
    - From bastion/worker to CP
    - From bastion/worker to Oneprovider
    - From CP to Oneprovider
13. Finally, run the ansible playbook via command ```   ```
14. Hopefully, everything goes well. Now check whether there is a config on the Oneprovider machine at path you specified in step 9. In case of the README, it's ```/home/debian/oneprovider_config/99-openfaas.config```. Make sure the file exists and move it to the appropriate folder, where Oneprovider reads its configs. In case of our dev provider ```oneprovider01-devel-onedata-e-infra-cz``` the path for reading the config by Oneprovider is ```/opt/onedata/oneprovider/persistence/etc/op_worker/config.d/``` The config looks like this(delete the comments):
    - 
    ```
    [
        {op_worker, [
            {openfaas_host, "78.128.235.174"}, # IP of your worker node
            {openfaas_port, 31112},
            {openfaas_function_namespace, "openfaas-fn"},
            {openfaas_admin_username, "admin"},
            {openfaas_admin_password, "your-password"}, # password you specified in step 8. under field 'openfaas_admin_password'
            {openfaas_function_constraints, []},
            {openfaas_function_labels, #{}},
            {openfaas_function_limits, #{}},
            {openfaas_function_annotations, #{}},
            {openfaas_function_requests, #{}},
            {openfaas_function_env, #{
                "read_timeout" => "604800s",
                "write_timeout" => "604800s",
                "exec_timeout" => "604800s"}
            },
            {openfaas_activity_feed_secret, "your-secret"} # secret you specified in step 8. under field 'openfaas_activity_feed_secret'
        ]}
    ]
    ```
15. Restart one provider to reload the config.
16. If everything goes well, your Oneprovider should enable button the 'Run Workflow' button on a file as depicted in the picture.
    - <img src="./docs/images/workflowButton.png" alt="alt text" width="1200" height="400"/>
17. You should see OpenFaaS namespaces deployed to kubernetes cluster with some running pods.

### Run your first workflow manually via onedata UI
1. Configure the workflow as described here [Workflow Demo README](./workflow-demo-hashes-of-the-files/README.md).
2. Upload the workflow json in the workflow UI menu - upload json file.
3. Right click on a file/folder and press 'Run Workflow' button.
4. Confifgure and run.
5. There should may be problems running the OpenFaaS  worker pod for the first time(the pod that actually does the job). In that case:
    - Open  by k9s your kubernetes 
    - Edit secret Mutatingwebhookconfigurations by deleting last 4 characters - 'Cg=='
    - Configure /etc/hosts properly
6. Now all your workflows should run properly.


