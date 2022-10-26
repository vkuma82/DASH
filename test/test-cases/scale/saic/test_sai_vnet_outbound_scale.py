import json
from pathlib import Path
from pprint import pprint

import pytest
import saichallenger.dataplane.snappi.snappi_traffic_utils as stu
from saichallenger.dataplane.ptf_testutils import (send_packet,
                                                   simple_udp_packet,
                                                   simple_vxlan_packet,
                                                   verify_no_other_packets,
                                                   verify_packet)

import dash_helper.vnet2vnet_helper as dh

current_file_dir = Path(__file__).parent
import dpugen
import os
# Constants for scale VNET outbound routing configuration
NUMBER_OF_VIP = 1
NUMBER_OF_DLE = 2
NUMBER_OF_ENI = 2
NUMBER_OF_EAM = NUMBER_OF_ENI
NUMBER_OF_ORE = 2  # Per ENI
NUMBER_OF_OCPE = 2  # Per ORE
NUMBER_OF_VNET = NUMBER_OF_ENI + (NUMBER_OF_ORE * NUMBER_OF_ENI)  # So far per ORE, but may be different
NUMBER_OF_IN_ACL_GROUP = 0
NUMBER_OF_OUT_ACL_GROUP = 0


# Scaled configuration
# Pay attention to the 'count', 'start', 'step' keywords.
# See README.md for details.
TEST_VNET_OUTBOUND_CONFIG_SCALE = {

    'DASH_VIP': {
        'vpe': {
            'count': NUMBER_OF_VIP,
            'SWITCH_ID': '$SWITCH_ID',
            'IPV4': {
                'count': NUMBER_OF_VIP,
                'start': '221.0.0.2',
                'step': '0.1.0.0'
            }
        }
    },

    'DASH_DIRECTION_LOOKUP': {
        'dle': {
            'count': NUMBER_OF_DLE,
            'SWITCH_ID': '$SWITCH_ID',
            'VNI': {
                'count': NUMBER_OF_DLE,
                'start': 5000,
                'step': 1000
            },
            'ACTION': 'SET_OUTBOUND_DIRECTION'
        }
    },

    'DASH_ACL_GROUP': {
        'in_acl_group_id': {
            'count': NUMBER_OF_IN_ACL_GROUP,
            'ADDR_FAMILY': 'IPv4'
        },
        'out_acl_group_id': {
            'count': NUMBER_OF_OUT_ACL_GROUP,
            'ADDR_FAMILY': 'IPv4'
        }
    },

    'DASH_VNET': {
        'vnet': {
            'VNI': {
                'count': NUMBER_OF_VNET,
                'start': 1000,
                'step': 1000
            }
        }
    },


    # DASH_ENI:{{eni}}
    'DASH_ENI_SCALE': {
        'name': {  # supports: substitution
            'substitution': {
                'base': 'eni#{0}',
                'params': {
                    0: {
                        'start': 11,
                        'step': 1,
                        'count': NUMBER_OF_ENI,
                    },
                },
                'count': NUMBER_OF_ENI,
            }
        },
        'eni_id': {  # supports: increment
            'increment': {
                'start': 11,
                'step': 1,
                'count': NUMBER_OF_ENI  # TODO: copy count from eni count or make variables
            }
        },
        'mac_address': {  # supports: increment
            'increment': {
                'start': '00:1A:C5:00:00:01',
                'step': '00:00:00:18:00:00',
                'count': NUMBER_OF_ENI  # TODO: copy count from eni count or make variables
            }
        },
        'address': {  # supports: increment
            'increment': {
                'start': '1.1.0.1',
                'step': '1.0.0.0',
                'count': NUMBER_OF_ENI  # TODO: copy count from eni count or make variables
            }
        },
        'underlay_ip': {  # supports: increment
            'increment': {
                'start': '221.0.1.1',
                'step': '0.0.0.1',
                'count': NUMBER_OF_ENI  # TODO: copy count from eni count or make variables
            }
        },
        'vnet': {  # supports: substitution
            'substitution': {
                'base': 'vnet#{0}',
                'params': {
                    0: {
                        'start': 1,
                        'step': 1,
                        'count': NUMBER_OF_ENI
                    },
                },
                'count': NUMBER_OF_ENI
            }
        },
    },
    'DASH_ENI_ETHER_ADDRESS_MAP': {
        'eam': {
            'count': NUMBER_OF_EAM,
            'SWITCH_ID': '$SWITCH_ID',
            'MAC': {
                'count': NUMBER_OF_EAM,
                #'start': '00:CC:CC:CC:00:00',
                'start': '00:1A:C5:00:00:01',
                'step': "00:00:00:00:00:01"
            },
            'ENI_ID': {
                'count': NUMBER_OF_ENI,
                'start': '$eni_#{0}'
            }
        }
    },

    'DASH_OUTBOUND_ROUTING': {
        'ore': {
            'count': NUMBER_OF_ENI * NUMBER_OF_ORE,  # Full count: OREs per ENI and VNET
            'SWITCH_ID': '$SWITCH_ID',
            'ACTION': 'ROUTE_VNET',
            'DESTINATION': {
                'count': NUMBER_OF_ORE,
                #'start': '10.1.1.0/31',
                'start': "1.128.0.1/9",
                'step': '0.0.0.2'
            },
            'ENI_ID': {
                'count': NUMBER_OF_ENI,
                'start': '$eni_#{0}',
                'delay': NUMBER_OF_ORE
            },
            'DST_VNET_ID': {
                'count': NUMBER_OF_VNET,
                'start': '$vnet_#{0}',
                'delay': NUMBER_OF_ORE
            }
        }
    },

    'DASH_OUTBOUND_CA_TO_PA': {
        'ocpe': {
            'count': (NUMBER_OF_ENI * NUMBER_OF_ORE) * NUMBER_OF_OCPE,  # 2 Per ORE
            'SWITCH_ID': '$SWITCH_ID',
            'DIP': {
                'count': NUMBER_OF_ORE * NUMBER_OF_OCPE,
                'start': '1.128.0.1',
                'step': '0.0.0.1'
            },
            'DST_VNET_ID': {
                'count': NUMBER_OF_VNET,
                'start': '$vnet_#{0}',
                'delay': NUMBER_OF_ORE
            },
            'UNDERLAY_DIP': {
                'count': NUMBER_OF_ENI * NUMBER_OF_ORE,
                'start': '221.0.1.1',
                'step': '0.0.0.1'
            },
            'OVERLAY_DMAC': {
                'count': NUMBER_OF_ENI * NUMBER_OF_ORE,
                'start': '00:1B:6E:00:00:01'
            },
            'USE_DST_VNET_VNI': True
        }
    }
}


class TestSaiVnetOutbound:

    def test_create_vnet_config(self, dpu):
        """Generate and apply configuration"""

        results = []
        conf = dpugen.sai.SaiConfig()
        #conf.mergeParams(TEST_VNET_OUTBOUND_CONFIG_SCALE)
        conf.generate()
        conf.write2File('json',os.path.join(current_file_dir,"abcd.json"))
        for item in conf.items():
            print (item)
            results.append(dpu.command_processor.process_command(item))

        # print("\n======= SAI commands RETURN values =======")
        # for cmd, res in zip(setup_commands, result):
        #     print(cmd['name'], cmd['type'], res)

    @pytest.mark.snappi
    def test_run_traffic_check_fixed_packets(self, dpu, dataplane):
        """
        Test with the fixed number of packets to send.
        packets_per_flow=1 means that each possible packet path will be verified using a single packet.
        NOTE: This test does not verify the correctness of the packets transformation.
        """

        #Generate traffic configuration, apply it and run.
        dh.scale_vnet_outbound_flows(dataplane, TEST_VNET_OUTBOUND_CONFIG_SCALE,
                                     packets_per_flow=1, flow_duration=0, pps_per_flow=10)
        dataplane.set_config()
        dataplane.start_traffic()

        # The following function waits for expected counters and fail if no success during time out.
        stu.wait_for(lambda: dh.check_flows_all_packets_metrics(dataplane, dataplane.flows,
                                                                name="Custom flow group", show=True)[0],
                    "Test", timeout_seconds=5)

    @pytest.mark.snappi
    def test_run_traffic_check_fixed_duration(self, dpu, dataplane):
        """
        Test with the fixed traffic duration to send.
        flow_duration sets the total duration of traffic. Number of packets is limited by PPS.
        For the HW PPS may be omitted and then it will send traffic on a line rate.
        NOTE: This test does not verify the correctness of the packets transformation.
        """
        test_duration = 5
        dh.scale_vnet_outbound_flows(dataplane, TEST_VNET_OUTBOUND_CONFIG_SCALE,
                                     packets_per_flow=0, flow_duration=test_duration, pps_per_flow=5)
        dataplane.set_config()
        dataplane.start_traffic()
        stu.wait_for(lambda: dh.check_flows_all_seconds_metrics(dataplane, dataplane.flows,
                                                                name="Custom flow group", show=True)[0],
                    "Test", timeout_seconds=test_duration + 1)

    def test_remove_vnet_config(self, dpu, dataplane):
        """
        Generate and remove configuration
        We generate configuration on remove stage as well to avoid storing giant objects in memory.
        """

        cleanup_commands = []
        conf = dpugen.sai.SaiConfig()
        conf.mergeParams(TEST_VNET_OUTBOUND_CONFIG_SCALE)
        conf.generate()
        # TODO: Items must be genrated in reverse order for removal.
        conf_items = list(conf.items())
        for item in reversed(conf_items):
            item['op'] = 'remove'
            cleanup_commands.append(dpu.command_processor.process_command(item))


        # print("\n======= SAI commands RETURN values =======")
        # for cmd, res in zip(cleanup_commands, result):
        #     print(cmd['name'], res)
