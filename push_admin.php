<?php
session_start();
$configFile = '/etc/mmdvm_push.json';
$serviceName = 'mmdvm_push.service';
$scriptPath = '/home/pi-star/MMDVM-Push-Notifier/mmdvm_push.py';
$updateScript = '/home/pi-star/MMDVM-Push-Notifier/update.sh';

// --- 获取实时版本号 ---
$version = trim(@shell_exec("python3 $scriptPath --version"));
if (empty($version)) { $version = 'v3.1.7'; }

// 磁盘读写控制
function set_disk($mode) { @shell_exec("sudo rpi-$mode"); }

// 初始化配置文件逻辑
if (!file_exists($configFile)) {
    set_disk('rw');
    file_put_contents($configFile, json_encode(["my_callsign"=>"BA4SMQ","min_duration"=>5.0,"ui_lang"=>"cn","ignore_list"=>"","focus_list"=>""], 192));
    set_disk('ro');
}

$config = json_decode(file_get_contents($configFile), true);

// 处理所有 POST 动作
if ($_SERVER['REQUEST_METHOD'] === 'POST' || isset($_GET['set_lang'])) {
    set_disk('rw');
    
    // 捕获当前语言状态
    $current_ui_lang = $_SESSION['pistar_push_lang'] ?? ($config['ui_lang'] ?? 'cn');

    if (isset($_GET['set_lang'])) {
        $config['ui_lang'] = $_GET['set_lang'];
        $_SESSION['pistar_push_lang'] = $_GET['set_lang'];
        file_put_contents($configFile, json_encode($config, 192));
    } elseif ($_POST['action'] === 'save') {
        // 【核心修复】：名单直接存为字符串，不再强制转换数组，支持分号和换行
        $newConfig = [
            "my_callsign" => strtoupper(trim($_POST['callsign'])),
            "min_duration" => floatval($_POST['min_duration']),
            "quiet_mode" => ["enabled"=>isset($_POST['qm_en']), "start"=>$_POST['qm_start'], "end"=>$_POST['qm_end']],
            "boot_push_enabled" => isset($_POST['boot_en']),
            "temp_alert_enabled" => isset($_POST['temp_en']),
            "temp_threshold" => floatval($_POST['temp_th']),
            "temp_interval" => intval($_POST['temp_int']),
            "temp_unit" => $_POST['temp_unit'] ?? 'C',
            "push_tg_enabled" => isset($_POST['tg_en']), "tg_token" => trim($_POST['tg_token']), "tg_chat_id" => trim($_POST['tg_chat_id']),
            "push_wx_enabled" => isset($_POST['wx_en']), "wx_token" => trim($_POST['wx_token']),
            "push_fs_enabled" => isset($_POST['fs_en']), "fs_webhook" => trim($_POST['fs_webhook']), "fs_secret" => trim($_POST['fs_secret']),
            "ignore_list" => trim($_POST['ignore_list']), 
            "focus_list" => trim($_POST['focus_list']),
            "ui_lang" => $current_ui_lang
        ];
        // 写入文件并更新内存变量
        if (file_put_contents($configFile, json_encode($newConfig, 448)) !== false) {
            $config = $newConfig;
            $alertMsg = ($current_ui_lang == 'cn') ? "✅ 设置已保存！" : "✅ Settings Saved!";
        }
    } elseif ($_POST['action'] === 'update') {
        // 执行一键更新脚本
        exec("sudo $updateScript 2>&1", $out, $res);
        $alertMsg = ($current_ui_lang == 'cn') ? "🚀 更新指令已发出！服务正在重启..." : "🚀 Update triggered! Service restarting...";
    }
    
    set_disk('ro');
    
    // 服务控制逻辑
    $action = $_POST['action'] ?? '';
    if (in_array($action, ['start', 'stop', 'restart'])) shell_exec("sudo systemctl $action $serviceName");
    
    if ($action === 'test') {
        $out = []; $res = 0;
        exec("sudo /usr/bin/python3 $scriptPath --test 2>&1", $out, $res);
        $foundSuccess = false;
        foreach ($out as $line) { if (stripos($line, 'Success') !== false) { $foundSuccess = true; break; } }
        $alertMsg = $foundSuccess ? 
            ($current_ui_lang == 'cn' ? "✅ 测试反馈: Success" : "✅ Test Feedback: Success") : 
            ($current_ui_lang == 'cn' ? "❌ 测试失败" : "❌ Test Failed");
    }
}

// 兼容函数：将 JSON 中的名单（无论是旧版数组还是新版字符串）正确显示在网页
function format_list_for_web($data) {
    if (is_array($data)) return implode("; ", $data);
    return (string)$data;
}

$current_lang = $_SESSION['pistar_push_lang'] ?? ($config['ui_lang'] ?? 'cn');
$is_cn = ($current_lang === 'cn');
$is_running = (strpos(shell_exec("sudo systemctl status $serviceName"), 'active (running)') !== false);

$lang = [
    'cn' => [
        'nav_dash'=>'仪表盘','nav_admin'=>'管理','nav_log'=>'日志','nav_power'=>'电源','nav_push'=>'推送设置','srv_ctrl'=>'服务控制','status'=>'状态','run'=>'运行中','stop'=>'已停止','btn_start'=>'启动','btn_stop'=>'停止','btn_res'=>'重启','btn_test'=>'发送测试','btn_save'=>'保存设置','btn_update'=>'检查更新','conf'=>'推送功能设置','my_call'=>'我的呼号','min_dur'=>'最小推送时长 (秒)','qm_en'=>'开启静音时段','qm_range'=>'静音时间范围',
        'boot_set'=>'启动通知','temp_set'=>'高温预警','en_boot'=>'设备启动提醒','en_temp'=>'高温预警','th_temp'=>'预警阈值','int_temp'=>'预警间隔 (分)',
        'tg_set'=>'Telegram 设置','wx_set'=>'微信 (PushPlus) 设置','fs_set'=>'飞书 (Feishu) 设置','en'=>'启用推送','ign_list'=>'忽略列表 (黑名单)','foc_list'=>'关注列表 (白名单)','list_hint'=>'呼号使用分号 (;) 或换行分隔'
    ],
    'en' => [
        'nav_dash'=>'Dashboard','nav_admin'=>'Admin','nav_log'=>'Live Logs','nav_power'=>'Power','nav_push'=>'Push Settings','srv_ctrl'=>'Service Control','status'=>'Status','run'=>'RUNNING','stop'=>'STOPPED','btn_start'=>'Start','btn_stop'=>'Stop','btn_res'=>'Restart','btn_test'=>'Send Test','btn_save'=>'SAVE SETTINGS','btn_update'=>'Update Now','conf'=>'Push Notifier Settings','my_call'=>'My Callsign','min_dur'=>'Min Duration (sec)','qm_en'=>'Quiet Mode','qm_range'=>'Quiet Time Range',
        'boot_set'=>'Boot Notice','temp_set'=>'Temp Alert','en_boot'=>'Enable Boot Push','en_temp'=>'Enable Temp Alert','th_temp'=>'Threshold','int_temp'=>'Interval (min)',
        'tg_set'=>'Telegram Settings','wx_set'=>'WeChat (PushPlus) Settings','fs_set'=>'Feishu Settings','en'=>'Enable','ign_list'=>'Ignore List','foc_list'=>'Focus List','list_hint'=>'Separate by semicolon (;) or newline'
    ]
][$current_lang];
?>
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml" lang="en">
<head>
    <meta http-equiv="Content-Type" content="text/html; charset=utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <link rel="stylesheet" type="text/css" href="css/pistar-css.php" />
    <title>Push Notifier Settings <?php echo $version; ?></title>
    <style type="text/css">
        textarea { width: 95%; height: 55px; font-family: monospace; font-size: 12px; }
        input[type="text"], input[type="password"] { width: 95%; height: 22px; }
        input[type="number"], input[type="time"] { height: 22px; }
        select { height: 24px; vertical-align: middle; }
        .time-box { width: 80px !important; }
        .num-box { width: 60px !important; }
        .btn-test { background: #b55; color: white; font-weight: bold; border: 1px solid #000; cursor: pointer; }
        .btn-update { background: #444; color: #fff; border: 1px solid #000; cursor: pointer; padding: 2px 10px; margin-left: 15px; }
        table.settings td:first-child { font-weight: bold; text-align: left !important; padding-left: 10px; width: 35%; }
        table.settings td:last-child { text-align: left !important; padding-left: 10px; }
    </style>
</head>
<body>
<div class="container">
    <div class="header">
        <div style="font-size: 8px; text-align: left; padding-left: 8px; float: left;">Hostname: <?php echo exec('hostname'); ?></div>
        <h1>Pi-Star Push Notifier - BA4SMQ (<?php echo $version; ?>)</h1>
        <p style="text-align: right; padding-right: 10px; color: #fff;">
            <a href="/" style="color: #fff;"><?php echo $lang['nav_dash']; ?></a> | 
            <a href="/admin/" style="color: #fff;"><?php echo $lang['nav_admin']; ?></a> | 
            <a href="/admin/power.php" style="color: #fff;"><?php echo $lang['nav_power']; ?></a> | 
            <a href="/admin/push_admin.php" style="color: #fff; font-weight: bold;"><?php echo $lang['nav_push']; ?></a> | 
            <a href="?set_lang=<?php echo $is_cn?'en':'cn';?>" style="color: #ffff00;">[<?php echo $is_cn?'English':'中文';?>]</a>
        </p>
    </div>
    <div class="contentwide">
        <?php if(isset($alertMsg)) echo "<div style='background:#ffffc0; color:#000; padding:5px; text-align:center; border:1px solid #666;'><b>$alertMsg</b></div>"; ?>
        <form method="post">
        <table class="settings">
            <thead><tr><th colspan="2"><?php echo $lang['srv_ctrl']; ?></th></tr></thead>
            <tr><td><?php echo $lang['status']; ?>:</td><td>
                <b style="color:<?php echo $is_running?'#008000':'#ff0000';?>"><?php echo $is_running ? $lang['run'] : $lang['stop']; ?></b>
                <button type="submit" name="action" value="update" class="btn-update"><?php echo $lang['btn_update']; ?></button>
            </td></tr>
            <tr><td>Action:</td><td>
                <button type="submit" name="action" value="start"><?php echo $lang['btn_start']; ?></button>
                <button type="submit" name="action" value="stop"><?php echo $lang['btn_stop']; ?></button>
                <button type="submit" name="action" value="restart"><?php echo $lang['btn_res']; ?></button>
            </td></tr>
            <thead><tr><th colspan="2"><?php echo $lang['conf']; ?></th></tr></thead>
            <tr><td><?php echo $lang['my_call']; ?>:</td><td><input type="text" name="callsign" value="<?php echo $config['my_callsign'];?>" /></td></tr>
            <tr><td><?php echo $lang['min_dur']; ?>:</td><td><input type="number" step="0.1" name="min_duration" class="num-box" value="<?php echo $config['min_duration'];?>" /></td></tr>
            <tr><td><?php echo $lang['qm_en']; ?>:</td><td><input type="checkbox" name="qm_en" <?php echo ($config['quiet_mode']['enabled']??false)?'checked':'';?> /></td></tr>
            <tr><td><?php echo $lang['qm_range']; ?>:</td><td>
                <input type="time" name="qm_start" class="time-box" value="<?php echo $config['quiet_mode']['start']??'23:00';?>" /> - 
                <input type="time" name="qm_end" class="time-box" value="<?php echo $config['quiet_mode']['end']??'07:00';?>" />
            </td></tr>
            <thead><tr><th colspan="2"><?php echo $lang['boot_set']; ?></th></tr></thead>
            <tr><td><?php echo $lang['en_boot']; ?>:</td><td><input type="checkbox" name="boot_en" <?php echo ($config['boot_push_enabled']??true)?'checked':'';?> /></td></tr>
            <thead><tr><th colspan="2"><?php echo $lang['temp_set']; ?></th></tr></thead>
            <tr><td><?php echo $lang['en_temp']; ?>:</td><td><input type="checkbox" name="temp_en" <?php echo ($config['temp_alert_enabled']??false)?'checked':'';?> /></td></tr>
            <tr><td><?php echo $lang['th_temp']; ?>:</td><td>
                <input type="number" step="0.1" name="temp_th" class="num-box" value="<?php echo $config['temp_threshold']??65.0;?>" />
                <select name="temp_unit">
                    <option value="C" <?php echo ($config['temp_unit']??'C')=='C'?'selected':'';?>>°C</option>
                    <option value="F" <?php echo ($config['temp_unit']??'C')=='F'?'selected':'';?>>°F</option>
                </select>
            </td></tr>
            <tr><td><?php echo $lang['int_temp']; ?>:</td><td><input type="number" name="temp_int" class="num-box" value="<?php echo $config['temp_interval']??30;?>" /></td></tr>
            <thead><tr><th colspan="2"><?php echo $lang['tg_set']; ?></th></tr></thead>
            <tr><td><?php echo $lang['en']; ?>:</td><td><input type="checkbox" name="tg_en" <?php echo ($config['push_tg_enabled']??false)?'checked':'';?> /></td></tr>
            <tr><td>Token:</td><td><input type="password" name="tg_token" value="<?php echo $config['tg_token']??'';?>" /></td></tr>
            <tr><td>Chat ID:</td><td><input type="text" name="tg_chat_id" value="<?php echo $config['tg_chat_id']??'';?>" /></td></tr>
            <thead><tr><th colspan="2"><?php echo $lang['wx_set']; ?></th></tr></thead>
            <tr><td><?php echo $lang['en']; ?>:</td><td><input type="checkbox" name="wx_en" <?php echo ($config['push_wx_enabled']??false)?'checked':'';?> /></td></tr>
            <tr><td>Token:</td><td><input type="password" name="wx_token" value="<?php echo $config['wx_token']??'';?>" /></td></tr>
            <thead><tr><th colspan="2"><?php echo $lang['fs_set']; ?></th></tr></thead>
            <tr><td><?php echo $lang['en']; ?>:</td><td><input type="checkbox" name="fs_en" <?php echo ($config['push_fs_enabled']??false)?'checked':'';?> /></td></tr>
            <tr><td>Webhook:</td><td><input type="text" name="fs_webhook" value="<?php echo $config['fs_webhook']??'';?>" /></td></tr>
            <tr><td>Secret:</td><td><input type="password" name="fs_secret" value="<?php echo $config['fs_secret']??'';?>" /></td></tr>
            <thead><tr><th colspan="2"><?php echo $lang['ign_list']; ?></th></tr></thead>
            <tr><td colspan="2" align="center"><textarea name="ignore_list" placeholder="<?php echo $lang['list_hint'];?>"><?php echo format_list_for_web($config['ignore_list']??'');?></textarea></td></tr>
            <thead><tr><th colspan="2"><?php echo $lang['foc_list']; ?></th></tr></thead>
            <tr><td colspan="2" align="center"><textarea name="focus_list" placeholder="<?php echo $lang['list_hint'];?>"><?php echo format_list_for_web($config['focus_list']??'');?></textarea></td></tr>
            <tr><td colspan="2" style="text-align: center !important; padding: 25px 0;">
                <button type="submit" name="action" value="save" style="width:130px; height:34px; font-weight:bold;"><?php echo $lang['btn_save']; ?></button>
                <button type="submit" name="action" value="test" class="btn-test" style="width:130px; height:34px; margin-left: 30px;"><?php echo $lang['btn_test']; ?></button>
            </td></tr>
        </table></form>
    </div>
    <div class="footer">Pi-Star / Pi-Star Dashboard <?php echo $version; ?>, Mod by BA4SMQ.</div>
</div>
</body></html>
