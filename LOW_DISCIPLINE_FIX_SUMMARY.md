Started parallel experiments at Mon Mar 30 13:35:09     2026

======================================================================
  健康管理模拟 - 9种实验组合（2026-01-23 设计）
======================================================================

  场景: diabetes
  天数: 45
  评分模式: nonlinear
  模式: 批量 + 并行(9)

  实验组合:
  ┌─────────────────┬──────────────────────────────────────┐
  │   初始健康分     │        自律程度                      │
  │                 │   high     medium     low           │
  ├─────────────────┼──────────────────────────────────────┤
  │   90 (高起点)   │   exp1      exp2       exp3         │
  │   75 (中起点)   │   exp4      exp5       exp6         │
  │   60 (低起点)   │   exp7      exp8       exp9         │
  └─────────────────┴──────────────────────────────────────┘

  警戒线: 30分
======================================================================

  可用API keys: 11 个
Traceback (most recent call last):
  File "E:\data\pythoncode\GenerativeAgentsCN\generative_agents\start_health_simulation.py", line 3795, in <module>
    main()
  File "E:\data\pythoncode\GenerativeAgentsCN\generative_agents\start_health_simulation.py", line 3690, in main
    run_all_experiments(
  File "E:\data\pythoncode\GenerativeAgentsCN\generative_agents\start_health_simulation.py", line 3512, in run_all_experiments
    p.start()
  File "D:\software\anaconda\envs\generative_agents_cn\Lib\multiprocessing\process.py", line 121, in start
    self._popen = self._Popen(self)
                  ^^^^^^^^^^^^^^^^^
  File "D:\software\anaconda\envs\generative_agents_cn\Lib\multiprocessing\context.py", line 224, in _Popen
    return _default_context.get_context().Process._Popen(process_obj)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "D:\software\anaconda\envs\generative_agents_cn\Lib\multiprocessing\context.py", line 337, in _Popen
    return Popen(process_obj)
           ^^^^^^^^^^^^^^^^^^
  File "D:\software\anaconda\envs\generative_agents_cn\Lib\multiprocessing\popen_spawn_win32.py", line 95, in __init__
    reduction.dump(process_obj, to_child)
  File "D:\software\anaconda\envs\generative_agents_cn\Lib\multiprocessing\reduction.py", line 60, in dump
    ForkingPickler(file, protocol).dump(obj)
AttributeError: Can't get local object 'run_all_experiments.<locals>.run_and_store'
Traceback (most recent call last):
  File "<string>", line 1, in <module>
  File "D:\software\anaconda\envs\generative_agents_cn\Lib\multiprocessing\spawn.py", line 122, in spawn_main
    exitcode = _main(fd, parent_sentinel)
               ^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "D:\software\anaconda\envs\generative_agents_cn\Lib\multiprocessing\spawn.py", line 132, in _main
    self = reduction.pickle.load(from_parent)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
EOFError: Ran out of input
