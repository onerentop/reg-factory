import os
import sys

# 让 tests/ 下的用例能 import 项目根的 config / common / ...
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
