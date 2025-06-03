import time
import threading
import os  # 引入os模块来处理文件路径

import nls
from test_utils import (TEST_ACCESS_TOKEN, TEST_ACCESS_APPKEY)

class TestSt:
    def __init__(self, tid, test_file):
        self.__th = threading.Thread(target=self.__test_run)
        self.__id = tid
        self.__test_file = test_file
   
    def loadfile(self, filename):
        try:
            print(f"【调试】尝试打开文件: {filename}")
            with open(filename, "rb") as f:
                self.__data = f.read()
            print(f"【调试】成功加载文件，大小: {len(self.__data)}字节")
        except FileNotFoundError:
            print(f"【错误】找不到文件: {filename}")
            raise
    
    def start(self):
        self.loadfile(self.__test_file)
        self.__th.start()

    def test_on_sentence_begin(self, message, *args):
        print("test_on_sentence_begin:{}".format(message))

    def test_on_sentence_end(self, message, *args):
        print("test_on_sentence_end:{}".format(message))

    def test_on_start(self, message, *args):
        print("test_on_start:{}".format(message))

    def test_on_error(self, message, *args):
        print("on_error args=>{}".format(args))

    def test_on_close(self, *args):
        print("on_close: args=>{}".format(args))

    def test_on_result_chg(self, message, *args):
        print("test_on_chg:{}".format(message))

    def test_on_completed(self, message, *args):
        print("on_completed:args=>{} message=>{}".format(args, message))


    def __test_run(self):
        print("thread:{} start..".format(self.__id))
        sr = nls.NlsSpeechTranscriber(
                    token=TEST_ACCESS_TOKEN,
                    appkey=TEST_ACCESS_APPKEY,
                    on_sentence_begin=self.test_on_sentence_begin,
                    on_sentence_end=self.test_on_sentence_end,
                    on_start=self.test_on_start,
                    on_result_changed=self.test_on_result_chg,
                    on_completed=self.test_on_completed,
                    on_error=self.test_on_error,
                    on_close=self.test_on_close,
                    callback_args=[self.__id]
                )
        print("{}: session start".format(self.__id))
        r = sr.start(aformat="pcm",
                enable_intermediate_result=True,
                enable_punctuation_prediction=True,
                enable_inverse_text_normalization=True)

        self.__slices = zip(*(iter(self.__data),) * 640)
        for i in self.__slices:
            sr.send_audio(bytes(i))
            time.sleep(0.01)

        sr.ctrl(ex={"test":"tttt"})
        time.sleep(1)

        r = sr.stop()
        print("{}: sr stopped:{}".format(self.__id, r))
        time.sleep(5)

def multiruntest(num=500):
    # 获取当前文件的路径
    current_file = os.path.abspath(__file__)
    # 获取当前文件所在的目录
    current_dir = os.path.dirname(current_file)
    # 构建测试音频文件的完整路径
    test_file_path = os.path.join(current_dir, "test1_16k_mono.pcm")
    
    print(f"【调试】测试文件路径: {test_file_path}")
    
    for i in range(0, num):
        name = "thread" + str(i)
        t = TestSt(name, test_file_path)
        t.start()


nls.enableTrace(True)
multiruntest(1)
