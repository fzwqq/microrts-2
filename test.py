import gym
import os
from microrts.rts_wrapper.envs.datatypes import List, Any
from microrts.rts_wrapper.envs.utils import unit_feature_encoder,network_action_translator, encoded_utt_dict, network_simulator, get_config
import torch
from microrts.algo.replay_buffer import ReplayBuffer
from microrts.algo.model import ActorCritic
import microrts.settings as settings
from microrts.rts_wrapper.envs.utils import action_sampler_v1
import argparse


from microrts.algo.utils import load_model
from microrts.algo.model import ActorCritic
from microrts.algo.replay_buffer import ReplayBuffer
from microrts.algo.a2c import A2C
from microrts.algo.agents import Agent

def self_play(env_id, render=0, opponent="socketAI", nn_path=None):
    """self play program
    
    Arguments:
        nn_path {str} -- path to model, if None, start from scratch
        map_size {tuple} -- (height, width)
    """     
    def logger(iter_idx, results):
        for k in results:
            writer.add_scalar(k, results[k], iter_idx)

    def memo_inserter(transitions):
        if transitions['reward'] > 0:
            print(transitions['reward'])
        memory.push(**transitions)
    
    
    get_config(env_id).render = render
    get_config(env_id).ai2_type = opponent

    env = gym.make(env_id)
    # assert env.ai1_type == "socketAI" and env.ai2_type == "socketAI", "This env is not for self-play"
    memory = ReplayBuffer(10000)

    start_from_scratch = nn_path is None
    
    players = env.players
 
    if start_from_scratch:
        nn = ActorCritic(env.map_size)
    else:
        nn = load_model(nn_path, env.map_size)

    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    # device = "cpu"
    nn.to(device)
    from torch.utils.tensorboard import SummaryWriter
    import time
    writer = SummaryWriter()
    iter_idx = 0
    

    agents = [Agent(model=nn) for _ in range(env.players_num)]
    algo = A2C(nn,lr=1e-4, weight_decay=3e-6, entropy_coef=.08, value_loss_coef=.1, log_interval=5, gamma=.99)
    # update_step = 64 #+ agents[0].random_rollout_steps
    # step = 0
    for epi_idx in range(env.max_episodes):
        obses_t = env.reset()  # p1 and p2 reset
        # print("reseted")
        start_time = time.time()
        players_G0 = [0, 0]
        while not obses_t[0].done:
            actions = []
            for i in range(len(players)):
                action = agents[i].think(callback=memo_inserter,way="stochastic", obses=obses_t[i], accelerator=device, mode="train")
                actions.append(action)
            obses_tp1 = env.step(actions)
            # step += 1

            if obses_tp1[0].done:
                for agent in agents:
                    agent.sum_up(callback=memo_inserter,way="stochastic", obses=obses_tp1[i], accelerator=device, mode="train")
                    agent.forget()
                

            # if len(memory) >= update_step:
            # # if step >= 5:
            #     algo.update(memory, iter_idx, device, logger)
            #     iter_idx += 1
                # step = 0


            # just for analisis
            for i in range(len(players)):
                players_G0[i] += obses_tp1[i].reward
            

            obses_t = obses_tp1

        algo.update(memory, iter_idx, device, logger)
        iter_idx += 1
        if (epi_idx + 1) % 100 == 0:
            torch.save(nn.state_dict(), os.path.join(settings.models_dir, "rl" + str(epi_idx) + ".pth"))

        print(players_G0)
        winner = obses_tp1[0].info["winner"]

        writer.add_scalar("Return_diff", players_G0[0] - players_G0[1] , epi_idx)
        writer.add_scalar("TimeStamp", obses_t[i].info["time_stamp"]  , epi_idx)

        print("Winner is:{}, FPS: {}".format(winner,obses_t[i].info["time_stamp"] / (time.time() - start_time)))
        
    print(env.setup_commands)
    torch.save(nn.state_dict(), os.path.join(settings.models_dir, "rl.pth"))



if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--env-id",
    )
    parser.add_argument(
        '--model-path', help='path of the model to be loaded')
    parser.add_argument(
        '--episodes',
        # default=10e6,
        type=int,
        default=10e8,
    )
    parser.add_argument(
        '-stc',
        # type=bool,
        action="store_true",
        default=False
    )
    parser.add_argument(
        '--recurrent',
        action="store_true",
        # type=bool,
        default=False,
    )
    torch.manual_seed(0)
    self_play("singleBattle-v0", render=0, opponent="socketAI")
    # self_play(nn_path=os.path.join(settings.models_dir, "rl999.pth"))
