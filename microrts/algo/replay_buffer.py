import numpy as np
import random
from dataclasses import dataclass
from microrts.rts_wrapper.envs.datatypes import GameState, PlayerAction
from typing import List, Any
from microrts.rts_wrapper.envs.units_name import *
from microrts.rts_wrapper.envs.utils import rd, unit_feature_encoder, encoded_utt_dict
from dacite import from_dict

import torch
# from numpy import random

@dataclass
class Transition:
    obs_t   : np.array
    # action  : List[Any] # list of (Unit, int(network_action) )
    action  : Any
    obs_tp1 : np.array
    reward  : float
    done    : bool

@dataclass
class Batches:
    states : np.array
    units: np.array
    actions: np.array
    next_states: np.array
    rewards: np.array
    done: np.array
    def to(self,device):
        done_masks = torch.FloatTensor(
                    [0.0 if _done==1  else 1.0 for _done in self.done]
                )
        # print(done_masks)
        return  torch.from_numpy(self.states).float().to(device), \
                torch.from_numpy(self.units).float().to(device), \
                torch.from_numpy(self.actions).long().to(device).unsqueeze(1), \
                torch.from_numpy(self.next_states).float().to(device), \
                torch.from_numpy(self.rewards).float().to(device).unsqueeze(1), \
                done_masks.to(device).unsqueeze(1)
                # torch.from_numpy(self.done).int().to(device).unsqueeze(1)
                


class ReplayBuffer(object):
    def __init__(self, size, frame_history_len=1):
        """Create Replay buffer
        Arguments:
            size {int} -- Storage capacity i.e. xax number of transitions to store in the buffer. When the buffer
            overflows the old memories are dropped.
        
        Keyword Arguments:
            frame_history_len {int} -- Num of frames taken for training input (default: {1})
        """

        self._storage = []
        self._maxsize = size
        self._next_idx = 0        # next pos to store the new data
        self._frame_history_len = frame_history_len

    def __len__(self):
        """Show current amount of samples
        
        Returns:
            int -- how many samples stored in the buffer?
        """
        return len(self._storage)
    
    def refresh(self):
        self._storage.clear()
        self._next_idx = 0
        
    def shuffle(self):
        random.shuffle(self._storage)
        
    def push(self, **kwargs):
        """Saves a transition   

        Arguments: 
            obs_t {np.array} -- [description]
            action {Unit and action pair} -- [description]
            reward {float} -- [description]
            obs_tp1 {np.array} -- [description]
            done {bool} -- [description]
        """
        trans = Transition(**kwargs)
        if self._next_idx >= len(self._storage):
            self._storage.append(trans)
        else:
            self._storage[self._next_idx] = trans
        self._next_idx = (self._next_idx + 1) % self._maxsize
    
    
    def _encode_sample(self, idxes):
        """[summary]
        
        Arguments:
            idxes {[type]} -- [description]
        
        Returns: Batch list of
            unit_types {np.array} -- [description]
            states {np.array} --
            units {np.array} -- unit features including utt for ac network input
            actions {np.array} -- network action for states
            next_states {np.array} --
            rewards {np.array} -- 
            done_masks {np.array}

        """
        # print(idxes)
        unit_types, states, units, actions, next_states, rewards, done_masks = [], [], [], [], [], [], []

        for i in idxes:
            transition = self._storage[i]
            
            state, unit_action, next_state, reward, done = transition.__dict__.values()
            map_size = state.shape[-2:]

            u, a = unit_action

            unit_types.append(u.type)
            states.append(state)
            units.append(np.hstack((unit_feature_encoder(u, map_size),encoded_utt_dict[u.type])))
            actions.append(a)
            next_states.append(next_state)
            rewards.append(reward)
            done_masks.append(done)

            
            # for u, a in unit_actions:
            #     unit_types.append(u.type)
            #     states.append(state)
            #     units.append(np.hstack((unit_feature_encoder(u, map_size),encoded_utt_dict[u.type])))
            #     actions.append(a)
            #     next_states.append(next_state)
            #     rewards.append(reward)
            #     done_masks.append(done)


            # states.append(state_encoder(gs=state, player=t_player))
            # units.append(unit_feature_encoder(u, state.pgs.height, state.pgs.width))
            # actions.append(game_action_translator(u, a))
            # unit_types.append(u.type)

        return  np.array(unit_types),   \
                np.array(states),       \
                np.array(units),        \
                np.array(actions),      \
                np.array(next_states),  \
                np.array(rewards),      \
                np.array(done_masks)


    def sample(self, batch_size):
        if batch_size == "all":
            batch_size = self.__len__()
            idxes = [i for i in range(batch_size)]
        else:
            idxes = [rd.randint(0, len(self._storage)) for _ in range(batch_size)]
        encoded_samples = self._encode_sample(idxes)
        return self._factorize(batch_size, encoded_samples)
        # samples = []
        # for i in idxes:
        #     samples.append(self._storage[i])
        # return samples
        # encoded_sample = self._encode_sample(idxes)
    
    # TODO:
    def _factorize(self, batch_size, batch) -> dict:
        """Rearrange the batch according to unit_type
        
        Arguments:
            batch_size {[type]} -- [description]
            batch {[type]} -- [description]
        
        Returns:
            dict -- dictionary of Batches
        """
        ans = {
                UNIT_TYPE_NAME_BASE:        [],
                UNIT_TYPE_NAME_BARRACKS:    [],
                UNIT_TYPE_NAME_WORKER:      [],
                UNIT_TYPE_NAME_LIGHT:       [],
                UNIT_TYPE_NAME_HEAVY:       [],
                UNIT_TYPE_NAME_RANGED:      [],
        }
        unit_types, states, units, actions, next_states, rewards, done_masks = batch
        for i in range(batch_size):
            ans[unit_types[i]].append((
                states[i],
                units[i],
                actions[i],
                next_states[i],
                rewards[i],
                done_masks[i]
                ))
        
        for key in ans:
            states, units, actions, next_states, rewards, done_masks = [], [], [], [], [], []
            if ans[key]:
                for v in ans[key]:
                    states.append(v[0])
                    units.append(v[1])
                    actions.append(v[2])
                    next_states.append(v[3])
                    rewards.append(v[4])
                    done_masks.append(v[5])
                
                temp = {
                    "states" : np.array(states),
                    "units": np.array(units),
                    "actions": np.array(actions),
                    "next_states":np.array(next_states),
                    "rewards":np.array(rewards),
                    "done":  np.array(done_masks)
                }
                ans[key] = Batches(**temp)
        return ans
    
    def fix_last_mask(self, done):
        # if has len >= 1
        if self._next_idx:
            self._storage[-1].done = done



if __name__ == '__main__':
    replay_buffer = ReplayBuffer(size=4)
    pass
