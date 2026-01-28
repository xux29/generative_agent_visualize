
import random
import datetime
import re
from string import Template
from pydantic import BaseModel
from collections import namedtuple
from typing import List, Tuple
from modules import utils
from modules.memory import Event


Result = namedtuple("Result", ["prompt", "callback", "failsafe", "return_type"])

class Scratch:
    def __init__(self, name, currently, config):
        self.name = name
        self.currently = currently
        self.config = config
        self.template_path = "data/prompts"

    def build_prompt(self, template, data):
        with open(f"{self.template_path}/{template}.txt", "r", encoding="utf-8") as file:
            file_content = file.read()

        template = Template(file_content)
        filled_content = template.substitute(data)

        return filled_content

    def _base_desc(self):
        return self.build_prompt(
            "base_desc",
            {
                "name": self.name,
                "age": self.config["age"],
                "innate": self.config["innate"],
                "learned": self.config["learned"],
                "lifestyle": self.config["lifestyle"],
                "daily_plan": self.config["daily_plan"],
                "date": utils.get_timer().daily_format_cn(),
                "currently": self.currently,
            }
        )

    def prompt_poignancy_event(self, event):
        prompt = self.build_prompt(
            "poignancy_event",
            {
                "base_desc": self._base_desc(),
                "agent": self.name,
                "event": event.get_describe(),
            }
        )

        class PoignancyEventResponse(BaseModel):
            res: int

        return Result(prompt, None, random.choice(list(range(10))) + 1, PoignancyEventResponse)

    def prompt_poignancy_chat(self, event):
        prompt = self.build_prompt(
            "poignancy_chat",
            {
                "base_desc": self._base_desc(),
                "agent": self.name,
                "event": event.get_describe(),
            }
        )

        class PoignancyChatResponse(BaseModel):
            res: int

        return Result(prompt, None, random.choice(list(range(10))) + 1, PoignancyChatResponse)

    def prompt_wake_up(self):
        prompt = self.build_prompt(
            "wake_up",
            {
                "base_desc": self._base_desc(),
                "lifestyle": self.config["lifestyle"],
                "agent": self.name,
            }
        )

        class wakeupResponse(BaseModel):
            res: int

        def _callback(response):
            value = response
            if value > 11:
                value = 11
            return value

        return Result(prompt, _callback, 8, wakeupResponse)

    def prompt_schedule_init(self, wake_up):
        prompt = self.build_prompt(
            "schedule_init",
            {
                "base_desc": self._base_desc(),
                "lifestyle": self.config["lifestyle"],
                "agent": self.name,
                "wake_up": wake_up,
            }
        )

        class schedule_initResponse(BaseModel):
            res: list[str]

        failsafe = [
            "早上6点起床并完成早餐的例行工作",
            "早上7点吃早餐",
            "早上8点看书",
            "中午12点吃午饭",
            "下午1点小睡一会儿",
            "晚上7点放松一下，看电视",
            "晚上11点睡觉",
        ]
        return Result(prompt, None, failsafe, schedule_initResponse)

    def prompt_schedule_daily(self, wake_up, daily_schedule):
        hourly_schedule = ""
        for i in range(wake_up):
            hourly_schedule += f"[{i}:00] 睡觉\n"
        for i in range(wake_up, 24):
            hourly_schedule += f"[{i}:00] <活动>\n"

        prompt = self.build_prompt(
            "schedule_daily",
            {
                "base_desc": self._base_desc(),
                "agent": self.name,
                "daily_schedule": "；".join(daily_schedule),
                "hourly_schedule": hourly_schedule,
            }
        )

        class schedule_dailyResponse(BaseModel):
            res: dict[str, str]

        failsafe = {
            "6:00": "起床并完成早晨的例行工作",
            "7:00": "吃早餐",
            "8:00": "读书",
            "9:00": "读书",
            "10:00": "读书",
            "11:00": "读书",
            "12:00": "吃午饭",
            "13:00": "小睡一会儿",
            "14:00": "小睡一会儿",
            "15:00": "小睡一会儿",
            "16:00": "继续工作",
            "17:00": "继续工作",
            "18:00": "回家",
            "19:00": "放松，看电视",
            "20:00": "放松，看电视",
            "21:00": "睡前看书",
            "22:00": "准备睡觉",
            "23:00": "睡觉",
        }

        def _callback(response):
            assert len(response) >= 5, "less than 5 schedules"
            return response

        return Result(prompt, _callback, failsafe, schedule_dailyResponse)

    def prompt_schedule_decompose(self, plan, schedule):
        def _plan_des(plan):
            start, end = schedule.plan_stamps(plan, time_format="%H:%M")
            return f'{start} 至 {end}，{self.name} 计划 {plan["describe"]}'

        indices = range(
            max(plan["idx"] - 1, 0), min(plan["idx"] + 2, len(schedule.daily_schedule))
        )

        start, end = schedule.plan_stamps(plan, time_format="%H:%M")
        increment = max(int(plan["duration"] / 100) * 5, 5)

        prompt = self.build_prompt(
            "schedule_decompose",
            {
                "base_desc": self._base_desc(),
                "agent": self.name,
                "plan": "；".join([_plan_des(schedule.daily_schedule[i]) for i in indices]),
                "increment": increment,
                "start": start,
                "end": end,
            }
        )

        class schedule_decomposeResponse(BaseModel):  
            res: List[Tuple[str, int]]

        def _callback(response):
            left = plan["duration"] - sum([s[1] for s in response])
            if left > 0:
                response.append((plan["describe"], left))
            return response

        failsafe = [(plan["describe"], 10) for _ in range(int(plan["duration"] / 10))]
        return Result(prompt, _callback, failsafe, schedule_decomposeResponse)

    def prompt_schedule_revise(self, action, schedule):
        plan, _ = schedule.current_plan()
        start, end = schedule.plan_stamps(plan, time_format="%H:%M")
        act_start_minutes = utils.daily_duration(action.start)
        original_plan, new_plan = [], []

        def _plan_des(start, end, describe):
            if not isinstance(start, str):
                start = start.strftime("%H:%M")
            if not isinstance(end, str):
                end = end.strftime("%H:%M")
            return "[{} 至 {}] {}".format(start, end, describe)

        for de_plan in plan["decompose"]:
            de_start, de_end = schedule.plan_stamps(de_plan, time_format="%H:%M")
            original_plan.append(_plan_des(de_start, de_end, de_plan["describe"]))
            if de_plan["start"] + de_plan["duration"] <= act_start_minutes:
                new_plan.append(_plan_des(de_start, de_end, de_plan["describe"]))
            elif de_plan["start"] <= act_start_minutes:
                new_plan.extend(
                    [
                        _plan_des(de_start, action.start, de_plan["describe"]),
                        _plan_des(
                            action.start, action.end, action.event.get_describe(False)
                        ),
                    ]
                )

        original_plan, new_plan = "\n".join(original_plan), "\n".join(new_plan)

        prompt = self.build_prompt(
            "schedule_revise",
            {
                "agent": self.name,
                "start": start,
                "end": end,
                "original_plan": original_plan,
                "duration": action.duration,
                "event": action.event.get_describe(),
                "new_plan": new_plan,
            }
        )

        class schedule_reviseResponse(BaseModel):
            res: List[Tuple[str, str, str]]

        def _callback(response):  
            # response已经是List[Tuple[str, str, str]]类型  
            # 格式: [(开始时间, 结束时间, 描述), ...]  
            decompose = []  
            for start, end, describe in response:  
                m_start = utils.daily_duration(utils.to_date(start, "%H:%M"))  
                m_end = utils.daily_duration(utils.to_date(end, "%H:%M"))  
                decompose.append(  
                    {  
                        "idx": len(decompose),  
                        "describe": describe,  
                        "start": m_start,  
                        "duration": m_end - m_start,  
                    }  
                )  
            return decompose

        return Result(prompt, _callback, plan["decompose"], schedule_reviseResponse)

    def prompt_determine_sector(self, describes, spatial, address, tile):
        live_address = spatial.find_address("living_area", as_list=True)[:-1]
        curr_address = tile.get_address("sector", as_list=True)

        prompt = self.build_prompt(
            "determine_sector",
            {
                "agent": self.name,
                "live_sector": live_address[-1],
                "live_arenas": ", ".join(i for i in spatial.get_leaves(live_address)),
                "current_sector": curr_address[-1],
                "current_arenas": ", ".join(i for i in spatial.get_leaves(curr_address)),
                "daily_plan": self.config["daily_plan"],
                "areas": ", ".join(i for i in spatial.get_leaves(address)),
                "complete_plan": describes[0],
                "decomposed_plan": describes[1],
            }
        )

        sectors = spatial.get_leaves(address)
        arenas = {}
        for sec in sectors:
            arenas.update(
                {a: sec for a in spatial.get_leaves(address + [sec]) if a not in arenas}
            )
        failsafe = random.choice(sectors)

        class determine_sectorResponse(BaseModel):
            res: str

        def _callback(response):  
            # response已经是str类型  
            # 验证sector是否在有效列表中，或进行映射  
            if response in sectors:  
                return response  
            if response in arenas:  
                return arenas[response]  
            for s in sectors:  
                if response.startswith(s):  
                    return s  
            return failsafe
        return Result(prompt, _callback, failsafe, determine_sectorResponse)

    def prompt_determine_arena(self, describes, spatial, address):
        prompt = self.build_prompt(
            "determine_arena",
            {
                "agent": self.name,
                "target_sector": address[-1],
                "target_arenas": ", ".join(i for i in spatial.get_leaves(address)),
                "daily_plan": self.config["daily_plan"],
                "complete_plan": describes[0],
                "decomposed_plan": describes[1],
            }
        )

        arenas = spatial.get_leaves(address)
        failsafe = random.choice(arenas)

        class determine_arenaResponse(BaseModel):  
            res: str

        def _callback(response):
            return response if response in arenas else failsafe

        return Result(prompt, _callback, failsafe, determine_arenaResponse)

    def prompt_determine_object(self, describes, spatial, address):
        objects = spatial.get_leaves(address)

        prompt = self.build_prompt(
            "determine_object",
            {
                "activity": describes[1],
                "objects": ", ".join(objects),
            }
        )

        failsafe = random.choice(objects)

        class determine_objectResponse(BaseModel):
            res: str
        def _callback(response):
            # pattern = ["The most relevant object from the Objects is: <(.+?)>", "<(.+?)>"]
            return response if response in objects else failsafe

        return Result(prompt, _callback, failsafe, determine_objectResponse)
    """
    def prompt_describe_emoji(self, describe):
        class describe_emojiResponse(BaseModel):
            res: str

        prompt = self.build_prompt(
            "describe_emoji",
            {
                "action": describe,
            }
        )

        def _callback(response):
            # 正则表达式：匹配大多数emoji
            emoji_pattern = u"([\U0001F600-\U0001F64F]|"   # 表情符号
            emoji_pattern += u"[\U0001F300-\U0001F5FF]|"   # 符号和图标
            emoji_pattern += u"[\U0001F680-\U0001F6FF]|"   # 运输和地图符号
            emoji_pattern += u"[\U0001F700-\U0001F77F]|"   # 午夜符号
            emoji_pattern += u"[\U0001F780-\U0001F7FF]|"   # 英镑符号
            emoji_pattern += u"[\U0001F800-\U0001F8FF]|"   # 合成扩展
            emoji_pattern += u"[\U0001F900-\U0001F9FF]|"   # 补充符号和图标
            emoji_pattern += u"[\U0001FA00-\U0001FA6F]|"   # 补充符号和图标
            emoji_pattern += u"[\U0001FA70-\U0001FAFF]|"   # 补充符号和图标
            emoji_pattern += u"[\U00002702-\U000027B0]+)"  # 杂项符号

            emoji = re.compile(emoji_pattern, flags=re.UNICODE).findall(response)
            if len(emoji) > 0:
                response = "Emoji: " + "".join(i for i in emoji)
            else:
                response = ""

            return parse_llm_output(response, ["Emoji: (.*)"])[:3]

        return {"prompt": prompt, "callback": _callback, "failsafe": "💭", "retry": 1}
    """
    def prompt_describe_event(self, subject, describe, address, emoji=None):
        prompt = self.build_prompt(
            "describe_event",
            {
                "action": describe,
            }
        )

        e_describe = describe.replace("(", "").replace(")", "").replace("<", "").replace(">", "")
        if e_describe.startswith(subject + "此时"):
            e_describe = e_describe.replace(subject + "此时", "")
        failsafe = Event(
            subject, "此时", e_describe, describe=describe, address=address, emoji=emoji
        )
        class describe_eventResponse(BaseModel):
            res: List[Tuple[str, str, str]]

        def _callback(response):  
            # response已经是List[Tuple[str, str, str]]类型  
            # 格式: [(主语, 谓语, 宾语), ...]  
            for subject, predicate, obj in response:  
                # 验证三元组不为空  
                if subject and predicate and obj:  
                    return Event(subject, predicate, obj, describe=describe, address=address, emoji=emoji)  
            return None
        return Result(prompt, _callback, failsafe, describe_eventResponse)

    def prompt_describe_object(self, obj, describe):
        prompt = self.build_prompt(
            "describe_object",
            {
                "object": obj,
                "agent": self.name,
                "action": describe,
            }
        )

        class describe_objectResponse(BaseModel):
            res: str

        failsafe = "空闲"
        return Result(prompt, None, failsafe, describe_objectResponse)

    def prompt_decide_chat(self, agent, other, focus, chats):
        def _status_des(a):
            event = a.get_event()
            if a.path:
                return f"{a.name} 正去往 {event.get_describe(False)}"
            return event.get_describe()

        context = "。".join(
            [c.describe for c in focus["events"]]
        )
        context += "\n" + "。".join([c.describe for c in focus["thoughts"]]) 
        date_str = utils.get_timer().get_date("%Y-%m-%d %H:%M:%S")
        chat_history = ""
        if chats:
            chat_history = f" {agent.name} 和 {other.name} 上次在 {chats[0].create} 聊过关于 {chats[0].describe} 的话题"
        a_des, o_des = _status_des(agent), _status_des(other)

        prompt = self.build_prompt(
            "decide_chat",
            {
                "context": context,
                "date": date_str,
                "chat_history": chat_history,
                "agent_status": a_des,
                "another_status": o_des,
                "agent": agent.name,
                "another": other.name,
            }
        )

        class decide_chatResponse(BaseModel):
            res: bool

        failsafe = False
        return Result(prompt, None, failsafe, decide_chatResponse)

    def prompt_decide_chat_terminate(self, agent, other, chats):
        conversation = "\n".join(["{}: {}".format(n, u) for n, u in chats])
        conversation = (
            conversation or "[对话尚未开始]"
        )

        prompt = self.build_prompt(
            "decide_chat_terminate",
            {
                "conversation": conversation,
                "agent": agent.name,
                "another": other.name,
            }
        )

        class decide_chat_terminateResponse(BaseModel):
            res: bool

        failsafe = False
        return Result(prompt, None, failsafe, decide_chat_terminateResponse)

    def prompt_decide_wait(self, agent, other, focus):
        example1 = self.build_prompt(
            "decide_wait_example",
            {
                "context": "简是丽兹的室友。2022-10-25 07:05，简和丽兹互相问候了早上好。",
                "date": "2022-10-25 07:09",
                "agent": "简",
                "another": "丽兹",
                "status": "简 正要去浴室",
                "another_status": "丽兹 已经在 使用浴室",
                "action": "使用浴室",
                "another_action": "使用浴室",
                "reason": "推理：简和丽兹都想用浴室。简和丽兹同时使用浴室会很奇怪。所以，既然丽兹已经在用浴室了，对简来说最好的选择就是等着用浴室。\n",
                "answer": "答案：<选项A>",
            }
        )
        example2 = self.build_prompt(
            "decide_wait_example",
            {
                "context": "山姆是莎拉的朋友。2022-10-24 23:00，山姆和莎拉就最喜欢的电影进行了交谈。",
                "date": "2022-10-25 12:40",
                "agent": "山姆",
                "another": "莎拉",
                "status": "山姆 正要去吃午饭",
                "another_status": "莎拉 已经在 洗衣服",
                "action": "吃午饭",
                "another_action": "洗衣服",
                "reason": "推理：山姆可能会在餐厅吃午饭。莎拉可能会去洗衣房洗衣服。由于山姆和莎拉需要使用不同的区域，他们的行为并不冲突。所以，由于山姆和莎拉将在不同的区域，山姆现在继续吃午饭。\n",
                "answer": "答案：<选项B>",
            }
        )

        def _status_des(a):
            event, loc = a.get_event(), ""
            if event.address:
                loc = " 在 {} 的 {}".format(event.address[-2], event.address[-1])
            if not a.path:
                return f"{a.name} 已经在 {event.get_describe(False)}{loc}"
            return f"{a.name} 正要去 {event.get_describe(False)}{loc}"

        context = ". ".join(
            [c.describe for c in focus["events"]]
        )
        context += "\n" + ". ".join([c.describe for c in focus["thoughts"]])

        task = self.build_prompt(
            "decide_wait_example",
            {
                "context": context,
                "date": utils.get_timer().get_date("%Y-%m-%d %H:%M"),
                "agent": agent.name,
                "another": other.name,
                "status": _status_des(agent),
                "another_status": _status_des(other),
                "action": agent.get_event().get_describe(False),
                "another_action": other.get_event().get_describe(False),
                "reason": "",
                "answer": "",
            }
        )

        prompt = self.build_prompt(
            "decide_wait",
            {
                "examples_1": example1,
                "examples_2": example2,
                "task": task,
            }
        )

        class decide_waitResponse(BaseModel):
            res: str

        def _callback(response):
            return "A" in response

        failsafe = False
        return Result(prompt, _callback, failsafe, decide_waitResponse)

    def prompt_summarize_relation(self, agent, other_name):
        nodes = agent.associate.retrieve_focus([other_name], 50)

        prompt = self.build_prompt(
            "summarize_relation",
            {
                "context": "\n".join(["{}. {}".format(idx, n.describe) for idx, n in enumerate(nodes)]),
                "agent": agent.name,
                "another": other_name,
            }
        )
        failsafe = agent.name + " 正在看着 " + other_name
        class summarize_relationResponse(BaseModel):
            res: str

        return Result(prompt, None, failsafe, summarize_relationResponse)

    def prompt_generate_chat(self, agent, other, relation, chats):
        focus = [relation, other.get_event().get_describe()]
        if len(chats) > 4:
            focus.append("; ".join("{}: {}".format(n, t) for n, t in chats[-4:]))
        nodes = agent.associate.retrieve_focus(focus, 15)
        memory = "\n- " + "\n- ".join([n.describe for n in nodes])
        chat_nodes = agent.associate.retrieve_chats(other.name)
        pass_context = ""
        for n in chat_nodes:
            delta = utils.get_timer().get_delta(n.create)
            if delta > 480:
                continue
            pass_context += f"{delta} 分钟前，{agent.name} 和 {other.name} 进行过对话。{n.describe}\n"

        address = agent.get_tile().get_address()
        if len(pass_context) > 0:
            prev_context = f'\n背景：\n"""\n{pass_context}"""\n\n'
        else:
            prev_context = ""
        curr_context = (
            f"{agent.name} {agent.get_event().get_describe(False)} 时，看到 {other.name} {other.get_event().get_describe(False)}。"
        )

        conversation = "\n".join(["{}: {}".format(n, u) for n, u in chats])
        conversation = (
            conversation or "[对话尚未开始]"
        )

        prompt = self.build_prompt(
            "generate_chat",
            {
                "agent": agent.name,
                "base_desc": self._base_desc(),
                "memory": memory,
                "address": f"{address[-2]}，{address[-1]}",
                "current_time": utils.get_timer().get_date("%H:%M"),
                "previous_context": prev_context,
                "current_context": curr_context,
                "another": other.name,
                "conversation": conversation,
            }
        )

        class generate_chat(BaseModel):  
            res: str

        failsafe = "嗯"
        return Result(prompt, None, failsafe, generate_chat)

    def prompt_generate_chat_check_repeat(self, agent, chats, content):
        conversation = "\n".join(["{}: {}".format(n, u) for n, u in chats])
        conversation = (
                conversation or "[对话尚未开始]"
        )

        class generate_chat_check_repeatResponse(BaseModel):  
            res: bool

        prompt = self.build_prompt(
            "generate_chat_check_repeat",
            {
                "conversation": conversation,
                "content": f"{agent.name}: {content}",
                "agent": agent.name,
            }
        )
        failsafe = False
        return Result(prompt, None, failsafe, generate_chat_check_repeatResponse)

    def prompt_summarize_chats(self, chats):
        conversation = "\n".join(["{}: {}".format(n, u) for n, u in chats])

        prompt = self.build_prompt(
            "summarize_chats",
            {
                "conversation": conversation,
            }
        )

        class summarize_chatsResponse(BaseModel):  
            res: str

        def _callback(response):
            return response.strip()

        if len(chats) > 1:
            failsafe = "{} 和 {} 之间的普通对话".format(chats[0][0], chats[1][0])
        else:
            failsafe = "{} 说的话没有得到回应".format(chats[0][0])

        return Result(prompt, _callback, failsafe, summarize_chatsResponse)

    def prompt_reflect_focus(self, nodes, topk):
        prompt = self.build_prompt(
            "reflect_focus",
            {
                "reference": "\n".join(["{}. {}".format(idx, n.describe) for idx, n in enumerate(nodes)]),
                "number": topk,
            }
        )

        class reflect_focusResponse(BaseModel):  
            res: List[str]

        failsafe = [
                "{} 是谁？".format(self.name),
                "{} 住在哪里？".format(self.name),
                "{} 今天要做什么？".format(self.name),
            ]
        return Result(prompt, None, failsafe, reflect_focusResponse)

    def prompt_reflect_insights(self, nodes, topk):
        prompt = self.build_prompt(
            "reflect_insights",
            {
                "reference": "\n".join(["{}. {}".format(idx, n.describe) for idx, n in enumerate(nodes)]),
                "number": topk,
            }
        )

        class reflect_insightsResponse(BaseModel):  
            res: List[Tuple[str, str]]

        def _callback(response):  
            insights = []  
            for insight, node_ids_str in response:  
                # 将字符串"1,2,3"转换为节点ID列表  
                indices = [int(i.strip()) for i in node_ids_str.split(",")]  
                node_ids = [nodes[i].node_id for i in indices if i < len(nodes)]  
                insights.append([insight.strip(), node_ids])  
            return insights

        failsafe = [
                [
                    "{} 在考虑下一步该做什么".format(self.name),
                    [nodes[0].node_id],
                ]
            ]
        return Result(prompt, _callback, failsafe, reflect_insightsResponse)

    def prompt_reflect_chat_planing(self, chats):
        all_chats = "\n".join(["{}: {}".format(n, c) for n, c in chats])

        prompt = self.build_prompt(
            "reflect_chat_planing",
            {
                "conversation": all_chats,
                "agent": self.name,
            }
        )

        class reflect_chat_planingResponse(BaseModel):  
            res: str

        failsafe = f"{self.name} 进行了一次对话"
        return Result(prompt, None, failsafe, reflect_chat_planingResponse)

    def prompt_reflect_chat_memory(self, chats):
        all_chats = "\n".join(["{}: {}".format(n, c) for n, c in chats])

        prompt = self.build_prompt(
            "reflect_chat_memory",
            {
                "conversation": all_chats,
                "agent": self.name,
            }
        )
        class reflect_chat_memoryResponse(BaseModel):  
            res: str

        failsafe = f"{self.name} 进行了一次对话"
        return Result(prompt, None, failsafe, reflect_chat_memoryResponse)

    def prompt_retrieve_plan(self, nodes):
        statements = [
            n.create.strftime("%Y-%m-%d %H:%M") + ": " + n.describe for n in nodes
        ]

        prompt = self.build_prompt(
            "retrieve_plan",
            {
                "description": "\n".join(statements),
                "agent": self.name,
                "date": utils.get_timer().get_date("%Y-%m-%d"),
            }
        )

        class retrieve_planResponse(BaseModel):
            res: List[str]

        failsafe = [r.describe for r in random.choices(nodes, k=5)]
        return Result(prompt, None, failsafe, retrieve_planResponse)

    def prompt_retrieve_thought(self, nodes):
        statements = [
            n.create.strftime("%Y-%m-%d %H:%M") + "：" + n.describe for n in nodes
        ]

        prompt = self.build_prompt(
            "retrieve_thought",
            {
                "description": "\n".join(statements),
                "agent": self.name,
            }
        )

        class retrieve_thoughtResponse(BaseModel):
            res: str

        failsafe = "{} 应该遵循昨天的日程".format(self.name)
        return Result(prompt, None, failsafe, retrieve_thoughtResponse)

    def prompt_retrieve_currently(self, plan_note, thought_note):
        time_stamp = (
            utils.get_timer().get_date() - datetime.timedelta(days=1)
        ).strftime("%Y-%m-%d")

        prompt = self.build_prompt(
            "retrieve_currently",
            {
                "agent": self.name,
                "time": time_stamp,
                "currently": self.currently,
                "plan": ". ".join(plan_note),
                "thought": thought_note,
                "current_time": utils.get_timer().get_date("%Y-%m-%d"),
            }
        )

        class retrieve_currentlyResponse(BaseModel):
            res: str

        failsafe = self.currently

        return Result(prompt, None, failsafe, retrieve_currentlyResponse)

    # ===== Health Management Prompts =====

    def prompt_health_generate_intention(self, health_status, forbidden_activities, retrieved_concepts, self_discipline, environment_constraints="无特殊限制", behavior_tendency="stable", is_in_relapse=False):
        """Generate Target's behavioral intention"""
        # 将复发状态转换为中文描述
        relapse_str = "是（正处于复发期，冲动强烈）" if is_in_relapse else "否"

        # 将行为倾向转换为中文描述
        tendency_map = {
            "improving": "improving（改善中）",
            "stable": "stable（稳定）",
            "declining": "declining（恶化中）",
            "relapsing": "relapsing（复发中）",
        }
        tendency_str = tendency_map.get(behavior_tendency, behavior_tendency)

        prompt = self.build_prompt(
            "health_generate_intention",
            {
                "name": self.name,
                "current_time": utils.get_timer().daily_format_cn(),
                "innate": self.config["innate"],
                "learned": self.config["learned"],
                "currently": self.currently,
                "health_status": health_status,
                "forbidden_activities": ", ".join(forbidden_activities),
                "retrieved_concepts": "\n".join([f"- {c}" for c in retrieved_concepts]),
                "self_discipline": self_discipline,
                "environment_constraints": environment_constraints,
                "behavior_tendency": tendency_str,
                "is_in_relapse": relapse_str,
            }
        )

        class HealthIntentionRes(BaseModel):
            activity: str
            duration: int
            compliance_threshold: int
            inner_monologue: str

        class HealthIntentionResponse(BaseModel):
            res: HealthIntentionRes

        failsafe = {
            "activity": "休息",
            "duration": 30,
            "compliance_threshold": 1,
            "inner_monologue": "我应该休息一下"
        }

        def _callback(response):
            return {
                "activity": response.activity,
                "duration": response.duration,
                "compliance_threshold": response.compliance_threshold,
                "inner_monologue": response.inner_monologue
            }

        return Result(prompt, _callback, failsafe, HealthIntentionResponse)

    def prompt_health_evaluate_strategy(self, target_name, relationship, target_health_status,
                                       target_intention, compliance_threshold, inner_monologue,
                                       target_today_log, strategy_preference):
        """Evaluate Manager's intervention strategy"""
        prompt = self.build_prompt(
            "health_evaluate_strategy",
            {
                "name": self.name,
                "current_time": utils.get_timer().daily_format_cn(),
                "innate": self.config["innate"],
                "strategy_preference": strategy_preference,
                "target_name": target_name,
                "relationship": relationship,
                "target_health_status": target_health_status,
                "target_intention": target_intention,
                "compliance_threshold": compliance_threshold,
                "inner_monologue": inner_monologue,
                "target_today_log": target_today_log,
            }
        )

        class HealthStrategyRes(BaseModel):
            level: int
            action: str
            timing: str
            reason: str

        class HealthStrategyResponse(BaseModel):
            res: HealthStrategyRes

        failsafe = {
            "level": 0,
            "action": "observe",
            "timing": "none",
            "reason": "继续观察"
        }

        def _callback(response):
            return {
                "level": response.level,
                "action": response.action,
                "timing": response.timing,
                "reason": response.reason
            }

        return Result(prompt, _callback, failsafe, HealthStrategyResponse)

    def prompt_health_generate_persuasion(self, target_name, target_intention, strategy_reason,
                                         relationship, target_personality):
        """Generate persuasion text"""
        prompt = self.build_prompt(
            "health_generate_persuasion",
            {
                "name": self.name,
                "target_name": target_name,
                "target_intention": target_intention,
                "strategy_reason": strategy_reason,
                "relationship": relationship,
                "your_personality": self.config["innate"],
                "target_personality": target_personality,
            }
        )

        class HealthPersuasionResponse(BaseModel):
            res: str

        failsafe = f"{target_name}，这样对你的健康不好。"

        return Result(prompt, None, failsafe, HealthPersuasionResponse)

    def prompt_health_react_persuasion(self, supervisor_name, your_intention, persuasion_text,
                                      strategy_reason, self_discipline, inner_monologue):
        """React to persuasion"""
        prompt = self.build_prompt(
            "health_react_persuasion",
            {
                "name": self.name,
                "your_intention": your_intention,
                "supervisor_name": supervisor_name,
                "persuasion_text": persuasion_text,
                "strategy_reason": strategy_reason,
                "your_personality": self.config["innate"],
                "self_discipline": self_discipline,
                "inner_monologue": inner_monologue,
            }
        )

        class HealthReactionRes(BaseModel):
            accept: bool
            response: str
            inner_thought: str

        class HealthReactionResponse(BaseModel):
            res: HealthReactionRes

        failsafe = {
            "accept": False,
            "response": "我知道了",
            "inner_thought": "我还是想做"
        }

        def _callback(response):
            return {
                "accept": response.accept,
                "response": response.response,
                "inner_thought": response.inner_thought
            }

        return Result(prompt, _callback, failsafe, HealthReactionResponse)

    def prompt_health_daily_reflection(self, day, target_name, monitoring_hours, day_log,
                                      intervention_log, health_score, score_breakdown):
        """Daily reflection for Manager"""
        prompt = self.build_prompt(
            "health_daily_reflection",
            {
                "name": self.name,
                "target_name": target_name,
                "day": day,
                "monitoring_hours": monitoring_hours,
                "day_log": day_log,
                "intervention_log": intervention_log,
                "health_score": health_score,
                "score_breakdown": score_breakdown,
            }
        )

        class HealthReflectionRes(BaseModel):
            today_summary: str
            strategy_effectiveness: str
            risk_patterns: List[str]
            tomorrow_focus: str
            strategy_adjustment: str

        class HealthReflectionResponse(BaseModel):
            res: HealthReflectionRes

        failsafe = {
            "today_summary": "今天的监督工作已完成",
            "strategy_effectiveness": "策略基本有效",
            "risk_patterns": [],
            "tomorrow_focus": "继续观察",
            "strategy_adjustment": "保持当前策略"
        }

        def _callback(response):
            return {
                "today_summary": response.today_summary,
                "strategy_effectiveness": response.strategy_effectiveness,
                "risk_patterns": response.risk_patterns,
                "tomorrow_focus": response.tomorrow_focus,
                "strategy_adjustment": response.strategy_adjustment
            }

        return Result(prompt, _callback, failsafe, HealthReflectionResponse)

    # ============================================================================
    # Batch Processing Prompts for Performance Optimization
    # ============================================================================

    def prompt_health_generate_intention_batch(self, day, num_slots, time_slots,
                                                health_status, forbidden_activities,
                                                self_discipline, environment_constraints,
                                                behavior_tendency, is_in_relapse):
        """
        批量生成一整天所有时间点的意图（性能优化）

        Args:
            day: 当前天数
            num_slots: 时间点数量
            time_slots: 时间点列表，如 ["21:00", "21:30", ...]
            health_status: 健康状态
            forbidden_activities: 禁止活动
            self_discipline: 自律程度
            environment_constraints: 环境约束
            behavior_tendency: 行为倾向
            is_in_relapse: 是否复发
        """
        relapse_str = "是（正处于复发期，冲动强烈）" if is_in_relapse else "否"
        tendency_map = {
            "improving": "improving（改善中）",
            "stable": "stable（稳定）",
            "declining": "declining（恶化中）",
            "relapsing": "relapsing（复发中）",
        }
        tendency_str = tendency_map.get(behavior_tendency, behavior_tendency)

        # 构建时间点字符串
        time_slots_str = ", ".join(time_slots)

        prompt = self.build_prompt(
            "health_generate_intention_batch",
            {
                "name": self.name,
                "current_date": utils.get_timer().get_date().strftime("%Y-%m-%d"),
                "day": day,
                "start_time": time_slots[0] if time_slots else "21:00",
                "end_time": time_slots[-1] if time_slots else "02:00",
                "num_slots": num_slots,
                "innate": self.config["innate"],
                "learned": self.config["learned"],
                "currently": self.currently,
                "health_status": health_status,
                "forbidden_activities": ", ".join(forbidden_activities),
                "self_discipline": self_discipline,
                "environment_constraints": environment_constraints,
                "behavior_tendency": tendency_str,
                "is_in_relapse": relapse_str,
                "time_slots": time_slots_str,
            }
        )

        class IntentionItem(BaseModel):
            time_slot: int
            time: str
            activity: str
            duration: int
            compliance_threshold: int
            inner_monologue: str

        class BatchIntentionResponse(BaseModel):
            res: List[IntentionItem]

        # 生成默认的failsafe
        failsafe = [
            {
                "time_slot": i,
                "time": time_slots[i] if i < len(time_slots) else f"{21 + i//2}:{(i%2)*30:02d}",
                "activity": "休息",
                "duration": 30,
                "compliance_threshold": 1,
                "inner_monologue": "我应该休息"
            }
            for i in range(num_slots)
        ]

        def _callback(response):
            return [
                {
                    "time_slot": item.time_slot,
                    "time": item.time,
                    "activity": item.activity,
                    "duration": item.duration,
                    "compliance_threshold": item.compliance_threshold,
                    "inner_monologue": item.inner_monologue
                }
                for item in response
            ]

        return Result(prompt, _callback, failsafe, BatchIntentionResponse)

    def prompt_health_evaluate_strategy_batch(self, day, target_name, target_profile,
                                               forbidden_activities, intentions_list,
                                               supervision_style, relationship,
                                               escalation_threshold,
                                               self_discipline="medium",
                                               health_score=75.0):
        """
        批量评估一整天所有意图的干预策略（性能优化）

        Args:
            day: 当前天数
            target_name: 被监督者名称
            target_profile: 被监督者档案
            forbidden_activities: 禁止活动
            intentions_list: 所有意图列表
            supervision_style: 监督风格
            relationship: 关系
            escalation_threshold: 升级阈值
            self_discipline: 被监督者自律程度
            health_score: 当前健康分
        """
        # 构建意图列表字符串
        intentions_str = "\n".join([
            f"- [{item['time']}] 意图: {item['activity']} (遵守难度: {item['compliance_threshold']}, 内心独白: {item['inner_monologue']})"
            for item in intentions_list
        ])

        prompt = self.build_prompt(
            "health_evaluate_strategy_batch",
            {
                "name": self.name,
                "day": day,
                "target_name": target_name,
                "target_profile": target_profile,
                "forbidden_activities": ", ".join(forbidden_activities),
                "intentions_list": intentions_str,
                "supervision_style": supervision_style,
                "relationship": relationship,
                "escalation_threshold": escalation_threshold,
                "self_discipline": self_discipline,
                "health_score": f"{health_score:.1f}",
            }
        )

        class StrategyItem(BaseModel):
            time_slot: int
            time: str
            level: int
            action: str
            reason: str

        class BatchStrategyResponse(BaseModel):
            res: List[StrategyItem]

        # 生成默认的failsafe
        failsafe = [
            {
                "time_slot": i,
                "time": item.get("time", f"{21 + i//2}:{(i%2)*30:02d}"),
                "level": 0,
                "action": "观察",
                "reason": "行为正常，无需干预"
            }
            for i, item in enumerate(intentions_list)
        ]

        def _callback(response):
            return [
                {
                    "time_slot": item.time_slot,
                    "time": item.time,
                    "level": item.level,
                    "action": item.action,
                    "reason": item.reason
                }
                for item in response
            ]

        return Result(prompt, _callback, failsafe, BatchStrategyResponse)
