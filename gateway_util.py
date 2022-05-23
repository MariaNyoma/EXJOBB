import paramiko
import re

def get_ssh(modem_hostname, modem_port, modem_username, modem_password):
    ssh=paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(hostname=modem_hostname, port=modem_port, username=modem_username, password=modem_password)
    return ssh

def read_and_copy_config(ssh,file):
    _, stdout, _ = ssh.exec_command('cat /lib/db/config/hw')
    output=stdout.readlines()
    f = open(file, "a")
    for line in output:
        f.write(line)
    f.close()
    return output

def reset_to_default(ssh):
    _,_,_ = ssh.exec_command('defaultreset')

#Parse config
def get_mapping_and_uci_command_to_change_config(config):
    mapping={}
    mapping['objects']=[]
    mapping['states']=[]
    mapping['LED']=[]
    mapping['LED_color']=[]
    mapping['LED_behavior']=[]

    command=''
    current_func=''
    records_to_delete=[]

    for line in config:
        #add test functions and remap existing ones
        if 'functions' in line:
            word_list=line.split()
            func=word_list[-1][1:-1]
            command+='uci -c /lib/db/config/ rename hw.led_' + func + '=led_' + func + '_test && '
            command+='uci -c /lib/db/config/ del_list hw.led_map.functions=' + func + ' && '
            command+='uci -c /lib/db/config/ add_list hw.led_map.functions=' + func + '_test && '
            continue

        if 'config led_map' in line:
            word_list=line.split()
            current_func=word_list[-1].replace('\'led_','')[:-1]
            continue

        #Collect mapping data
        if 'led_action' in line and current_func.capitalize:            
            mapping['objects'].append([current_func + '_test'])
            word_list=line.split()
            behavior=word_list[-1][:-1]
            color=word_list[-3].split('_')[-1]
            LED=word_list[-3].split('_')[0][1:]
            state=word_list[1].split('_')[-1]
            mapping['states'].append([state])
            mapping['LED'].append(LED)
            mapping['LED_color'].append(color)
            mapping['LED_behavior'].append(behavior)
            continue

        #if there are super functions
        if 'super' in line:            
            word_list=line.split(' \'')
            super_state=word_list[0].split('_')[-1]
            objects_and_states=word_list[-1][:-2].split(', ')
            objects,states=[],[]
            for o_a_s in objects_and_states:
                objects.append(o_a_s.split('_')[0]+'_test')
                states.append(o_a_s.split('_')[1])
            for idx,(o,s) in enumerate(zip(mapping['objects'],mapping['states'])):
                if o==[current_func+'_test'] and s==[super_state]:
                    LED=mapping['LED'][idx]
                    color=mapping['LED_color'][idx]
                    behavior=mapping['LED_behavior'][idx]
                    if idx not in records_to_delete:
                        records_to_delete.append(idx)
            mapping['objects'].append(objects)
            mapping['states'].append(states)
            mapping['LED'].append(LED)
            mapping['LED_color'].append(color)
            mapping['LED_behavior'].append(behavior)
            val='\''
            for (o,s) in zip(objects,states):
                val += o + '_' + s + ', '
            val=val[:-2]+'\''
            command+='uci -c /lib/db/config/ add_list hw.led_' + current_func + '_test.super_' + super_state + '=' + val + ' && '
    
    for i,r in enumerate(records_to_delete):
        del mapping['objects'][r-i]
        del mapping['states'][r-i]
        del mapping['LED'][r-i]
        del mapping['LED_color'][r-i]
        del mapping['LED_behavior'][r-i]
           
    command += 'uci -c /lib/db/config/ commit && /etc/init.d/peripheral_manager restart'
    return (mapping, command)

def get_command_and_expected_behavior_dict(mapping,functions):
    commands_behavior_dict={}
    for idx in range(len(mapping['objects'])):
        command=''
        for (o,s) in zip(mapping['objects'][idx],mapping['states'][idx]):      
            if o not in functions:
                break
            command+='ubus call led.' + o + ' set "{\\"state\\" : \\"' + s + '\\"}" && '
        if command=='':
            continue
        command=command[:-3]
        commands_behavior_dict[command]=(mapping['LED'][idx],mapping['LED_color'][idx],mapping['LED_behavior'][idx])
    return commands_behavior_dict

def revert(ssh):
    stdin, stdout, stderr =ssh.exec_command('uci -c /lib/db/config/ revert hw')
    return stderr.readlines()==[]
    
def run_uci_command(ssh, command):
    stdin, stdout, stderr =ssh.exec_command(command)
    return stderr.readlines()==[]