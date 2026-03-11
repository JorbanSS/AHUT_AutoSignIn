API_BASE_URL = "https://xskq.ahut.edu.cn/api"
WEB_DICT = {
    "token_api": f"{API_BASE_URL}/flySource-auth/oauth/token",
    "task_id_api": f"{API_BASE_URL}/flySource-yxgl/dormSignTask/getStudentTaskPage?userDataType=student&current=1&size=15",
    "auth_check_api": f"{API_BASE_URL}/flySource-base/wechat/getWechatMpConfig"
    "?configUrl=https://xskq.ahut.edu.cn/wise/pages/ssgl/dormsign"
    "?taskId={TASK_ID}&autoSign=1&scanSign=0&userId={STUDENT_ID}",
    "apiLog_api": f"{API_BASE_URL}/flySource-base/apiLog/save?menuTitle=%E6%99%9A%E5%AF%9D%E7%AD%BE%E5%88%B0",
    "sign_in_api": f"{API_BASE_URL}/flySource-yxgl/dormSignRecord/add",
}

UA_LIST = [
    "Mozilla/5.0 (Linux; Android 15; MIX Fold 4 Build/TKQ1.240502.001; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/128.0.6613.137 Mobile Safari/537.36 MicroMessenger/8.0.61.2660(0x28003D37) WeChat/arm64 Weixin NetType/WIFI Language/zh_CN ABI/arm64",
    "Mozilla/5.0 (Linux; Android 15; LYA-AL10 Build/HUAWEILYA-AL10; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/128.0.6613.137 Mobile Safari/537.36 MicroMessenger/8.0.61.2660(0x28003D37) WeChat/arm64 Weixin NetType/5G Language/zh_CN ABI/arm64",
    "Mozilla/5.0 (Linux; Android 15; SM-S938B Build/TP1A.240205.004; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/128.0.6613.137 Mobile Safari/537.36 MicroMessenger/8.0.61.2660(0x28003D37) WeChat/arm64 Weixin NetType/WIFI Language/zh_CN ABI/arm64",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 19_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 MicroMessenger/8.0.61(0x18003D29) NetType/WIFI Language/zh_CN",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 19_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 MicroMessenger/8.0.61(0x18003D29) NetType/5G Language/zh_CN",
]
