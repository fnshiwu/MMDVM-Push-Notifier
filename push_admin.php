<?php
session_start();
$configFile = '/etc/mmdvm_push.json';
$serviceName = 'mmdvm_push.service';
$scriptPath = '/home/pi-star/MMDVM-Push-Notifier/mmdvm_push.py';
$updateScript = '/home/pi-star/MMDVM-Push-Notifier/update.sh';

$accept = $_SERVER['HTTP_ACCEPT_LANGUAGE'] ?? '';
$detected_lang = (stripos($accept, 'zh') !== false) ? 'cn' : 'en';

// =========================
// Pi-Star Version Detection | Pi-Star 版本检测
// =========================
$pistar_version = 'unknown';
$is_bookworm = false;
if (file_exists('/etc/pistar-release')) {
    $pistar_release = @file_get_contents('/etc/pistar-release');
    if ($pistar_release !== false && preg_match('/Version=([0-9.]+)/', $pistar_release, $matches)) {
        $pistar_version = $matches[1];
    }
}
if (file_exists('/usr/lib/python3.11/EXTERNALLY-MANAGED') || 
    file_exists('/usr/lib/python3.9/EXTERNALLY-MANAGED') ||
    (file_exists('/etc/debian_version') && strpos(@file_get_contents('/etc/debian_version'), '12') === 0)) {
    $is_bookworm = true;
}

// Version retrieval | 获取实时版本号
$version_raw = @shell_exec("python3 $scriptPath --version");
$version = ($version_raw !== null) ? trim($version_raw) : 'unknown';
if (empty($version)) { $version = 'unknown'; }

// Disk read/write control | 磁盘读写控制
function set_disk($mode) { 
    $paths = [
        "/usr/local/sbin/rpi-$mode",
        "/usr/local/bin/rpi-$mode",
        "/usr/bin/rpi-$mode"
    ];
    foreach ($paths as $path) {
        if (file_exists($path)) {
            @shell_exec("sudo $path");
            break;
        }
    }
    @shell_exec("sudo mount -o remount,$mode / 2>/dev/null"); 
}

// Helper to clean quotes from token input | Token 清洗辅助函数
function clean_input_token($val) {
    return trim((string)$val, " \t\n\r\0\x0B\"'");
}

// Initialize configuration file | 初始化配置文件
if (!file_exists($configFile)) {
    set_disk('rw');
    file_put_contents($configFile, json_encode(["my_callsign"=>"BA4SMQ","min_duration"=>5.0,"ui_lang"=>$detected_lang,"ignore_list"=>"","focus_list"=>""], 192));
    set_disk('ro');
}

$config = json_decode(file_get_contents($configFile), true);
if (!isset($config['ui_lang']) || $config['ui_lang'] === '') {
    set_disk('rw');
    $config['ui_lang'] = $detected_lang;
    file_put_contents($configFile, json_encode($config, 192));
    set_disk('ro');
}

$csrfToken = $_SESSION['csrf_token'] ?? bin2hex(random_bytes(32));
$_SESSION['csrf_token'] = $csrfToken;

// Handle POST actions | 处理所有 POST 动作
if ($_SERVER['REQUEST_METHOD'] === 'POST' || isset($_GET['set_lang'])) {
    set_disk('rw');

    $current_ui_lang = $_SESSION['pistar_push_lang'] ?? ($config['ui_lang'] ?? 'cn');
    $valid_csrf = true;
    if ($_SERVER['REQUEST_METHOD'] === 'POST' && !isset($_GET['set_lang'])) {
        $valid_csrf = isset($_POST['csrf_token']) && hash_equals($_SESSION['csrf_token'] ?? '', $_POST['csrf_token']);
    }

    $msg = null;

    if (isset($_GET['set_lang'])) {
        $config['ui_lang'] = $_GET['set_lang'];
        $_SESSION['pistar_push_lang'] = $_GET['set_lang'];
        file_put_contents($configFile, json_encode($config, 192));
    } elseif (isset($_POST['action']) && $_POST['action'] === 'save' && $valid_csrf) {
        $newConfig = [
            "my_callsign" => strtoupper(trim($_POST['callsign'])),
            "min_duration" => floatval($_POST['min_duration']),
            "quiet_mode" => ["enabled"=>isset($_POST['qm_en']), "start"=>$_POST['qm_start'], "end"=>$_POST['qm_end']],
            "boot_push_enabled" => isset($_POST['boot_en']),
            "temp_alert_enabled" => isset($_POST['temp_en']),
            "temp_threshold" => floatval($_POST['temp_th']),
            "temp_interval" => intval($_POST['temp_int']),
            "temp_unit" => $_POST['temp_unit'] ?? 'C',
            "push_tg_enabled" => isset($_POST['tg_en']), 
            "tg_token" => clean_input_token($_POST['tg_token'] ?? ''), 
            "tg_chat_id" => clean_input_token($_POST['tg_chat_id'] ?? ''),
            "push_wx_enabled" => isset($_POST['wx_en']), 
            "wx_token" => clean_input_token($_POST['wx_token'] ?? ''),
            "push_fs_enabled" => isset($_POST['fs_en']), 
            "fs_webhook" => clean_input_token($_POST['fs_webhook'] ?? ''), 
            "fs_secret" => clean_input_token($_POST['fs_secret'] ?? ''),
            "ignore_list" => trim($_POST['ignore_list']), 
            "focus_list" => trim($_POST['focus_list']),
            "ui_lang" => $current_ui_lang
        ];
        $writeRes = file_put_contents($configFile, json_encode($newConfig, 448));
        if ($writeRes !== false) {
            $config = $newConfig;
            $msg = ($current_ui_lang == 'cn') ? "✅ 设置已保存！" : "✅ Settings Saved!";
        } else {
            $msg = ($current_ui_lang == 'cn') ? "❌ 保存失败：磁盘只读或权限不足" : "❌ Save failed: read-only filesystem or permission denied.";
        }
    } elseif (isset($_POST['action']) && $_POST['action'] === 'update' && $valid_csrf) {
        exec("sudo $updateScript > /dev/null 2>&1 &");
        $msg = ($current_ui_lang == 'cn') ? "🚀 更新在后台进行中，请稍候刷新查看版本..." : "🚀 Update started in background, please refresh later...";
    } elseif (isset($_POST['action']) && !$valid_csrf) {
        $msg = ($current_ui_lang == 'cn') ? "❌ CSRF 校验失败" : "❌ CSRF validation failed";
    }

    set_disk('ro');

    // Service control logic | 服务控制逻辑
    $action = $_POST['action'] ?? '';
    if ($valid_csrf && in_array($action, ['start', 'stop', 'restart'])) {
        @shell_exec("sudo systemctl $action $serviceName 2>&1");
        // 控制服务后短暂暂停 0.5 秒给 systemd 反应时间
        usleep(500000); 
    }

    if ($valid_csrf && $action === 'test') {
        $out = []; $res = 0;
        exec("sudo /usr/bin/python3 $scriptPath --test 2>&1", $out, $res);
        $foundSuccess = false;
        foreach ($out as $line) { if (stripos($line, 'Success') !== false) { $foundSuccess = true; break; } }
        $msg = $foundSuccess ? 
            ($current_ui_lang == 'cn' ? "✅ 测试反馈: Success" : "✅ Test Feedback: Success") : 
            ($current_ui_lang == 'cn' ? "❌ 测试失败" : "❌ Test Failed");
    }

    if ($msg) {
        $_SESSION['alert_msg'] = $msg;
    }
    header("Location: " . $_SERVER['PHP_SELF']);
    exit;
}

if (isset($_SESSION['alert_msg'])) {
    $alertMsg = $_SESSION['alert_msg'];
    unset($_SESSION['alert_msg']);
}

function format_list_for_web($data) {
    if (is_array($data)) return implode("; ", $data);
    return (string)$data;
}

$current_lang = $_SESSION['pistar_push_lang'] ?? ($config['ui_lang'] ?? 'cn');
$is_cn = ($current_lang === 'cn');

// Service status check | 服务状态检查
$status_raw = @shell_exec("sudo systemctl status $serviceName --no-pager 2>&1");
$is_running = ($status_raw !== null) ? (strpos($status_raw, 'active (running)') !== false) : false;

// Health check | 健康检查
$healthRaw = @shell_exec("python3 $scriptPath --health 2>&1");
$health = ($healthRaw !== null) ? json_decode($healthRaw, true) : null;
if (!is_array($health)) {
    $health = [
        "version" => $version,
        "app_log_dir" => "",
        "app_log_writable" => false,
        "mmdvm_log_dir" => "/var/log/pi-star/",
        "mmdvm_log_exists" => false,
        "config_exists" => file_exists($configFile),
        "config_valid" => is_array($config) && count($config) > 0,
        "time" => date('c')
    ];
}
$yes = $is_cn ? '是' : 'Yes';
$no = $is_cn ? '否' : 'No';

$lang = [
    'cn' => [
        'nav_dash'=>'仪表盘','nav_admin'=>'管理','nav_log'=>'日志','nav_power'=>'电源','nav_push'=>'推送设置','srv_ctrl'=>'服务控制','status'=>'状态','run'=>'运行中','stop'=>'已停止','btn_start'=>'启动','btn_stop'=>'停止','btn_res'=>'重启','btn_test'=>'发送测试','btn_save'=>'保存设置','btn_update'=>'检查更新','conf'=>'推送功能设置','my_call'=>'我的呼号','min_dur'=>'最小推送时长 (秒)','qm_en'=>'开启静音时段','qm_range'=>'静音时间范围',
        'boot_set'=>'启动通知','temp_set'=>'高温预警','en_boot'=>'设备启动提醒','en_temp'=>'高温预警','th_temp'=>'预警阈值','int_temp'=>'预警间隔 (分)',
        'tg_set'=>'Telegram 设置','wx_set'=>'微信 (PushPlus) 设置','fs_set'=>'飞书 (Feishu) 设置','en'=>'启用推送','ign_list'=>'忽略列表 (黑名单)','foc_list'=>'关注列表 (白名单)','list_hint'=>'仅呼号，使用"；"分隔'
    ],
    'en' => [
        'nav_dash'=>'Dashboard','nav_admin'=>'Admin','nav_log'=>'Live Logs','nav_power'=>'Power','nav_push'=>'Push Settings','srv_ctrl'=>'Service Control','status'=>'Status','run'=>'RUNNING','stop'=>'STOPPED','btn_start'=>'Start','btn_stop'=>'Stop','btn_res'=>'Restart','btn_test'=>'Send Test','btn_save'=>'SAVE SETTINGS','btn_update'=>'Update Now','conf'=>'Push Notifier Settings','my_call'=>'My Callsign','min_dur'=>'Min Duration (sec)','qm_en'=>'Quiet Mode','qm_range'=>'Quiet Time Range (HH:mm, 24-hour format)',
        'boot_set'=>'Boot Notice','temp_set'=>'Temp Alert','en_boot'=>'Enable Boot Push','en_temp'=>'Enable Temp Alert','th_temp'=>'Threshold','int_temp'=>'Interval (min)',
        'tg_set'=>'Telegram Settings','wx_set'=>'WeChat (PushPlus) Settings','fs_set'=>'Feishu Settings','en'=>'Enable','ign_list'=>'Ignore List','foc_list'=>'Focus List','list_hint'=>'Callsigns only; separate by semicolon (;)'
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
        .version-info { font-size: 11px; color: #aaa; text-align: right; padding-right: 10px; }
    </style>
</head>
<body>
<div class="container">
    <div class="header">
        <div style="font-size: 8px; text-align: left; padding-left: 8px; float: left;">Hostname: <?php echo htmlspecialchars(exec('hostname'), ENT_QUOTES, 'UTF-8'); ?></div>
        <h1>Pi-Star Push Notifier - BA4SMQ (<?php echo $version; ?>)</h1>
        <p style="text-align: right; padding-right: 10px; color: #fff;">
            <a href="/" style="color: #fff;"><?php echo $lang['nav_dash']; ?></a> | 
            <a href="/admin/" style="color: #fff;"><?php echo $lang['nav_admin']; ?></a> | 
            <a href="/admin/power.php" style="color: #fff;"><?php echo $lang['nav_power']; ?></a> | 
            <a href="/admin/push_admin.php" style="color: #fff; font-weight: bold;"><?php echo $lang['nav_push']; ?></a> | 
            <a href="?set_lang=<?php echo $is_cn?'en':'cn';?>" style="color: #ffff00;">[<?php echo $is_cn?'English':'中文';?>]</a>
        </p>
        <div class="version-info">
            Pi-Star: <?php echo htmlspecialchars($pistar_version, ENT_QUOTES, 'UTF-8'); ?> 
            <?php if ($is_bookworm) echo '| Bookworm'; ?>
        </div>
    </div>
    <div class="contentwide">
        <?php if(isset($alertMsg)) echo "<div style='background:#ffffc0; color:#000; padding:5px; text-align:center; border:1px solid #666;'><b>".htmlspecialchars($alertMsg, ENT_QUOTES, 'UTF-8')."</b></div>"; ?>
        <form method="post">
        <input type="hidden" name="csrf_token" value="<?php echo htmlspecialchars($csrfToken, ENT_QUOTES, 'UTF-8'); ?>" />
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
            <thead><tr><th colspan="2"><?php echo $is_cn?'健康状态':'Health Status'; ?></th></tr></thead>
            <tr><td><?php echo $is_cn?'版本':'Version'; ?>:</td><td><?php echo htmlspecialchars($health['version']??$version, ENT_QUOTES, 'UTF-8'); ?></td></tr>
            <tr><td><?php echo $is_cn?'Pi-Star 版本':'Pi-Star Version'; ?>:</td><td><?php echo htmlspecialchars($pistar_version, ENT_QUOTES, 'UTF-8'); ?></td></tr>
            <tr><td><?php echo $is_cn?'系统':'OS'; ?>:</td><td><?php echo $is_bookworm ? 'Debian 12 (Bookworm)' : 'Debian 11 (Bullseye) or earlier'; ?></td></tr>
            <tr><td><?php echo $is_cn?'MMDVM 日志目录':'MMDVM Log Dir'; ?>:</td><td><?php echo htmlspecialchars($health['mmdvm_log_dir']??'', ENT_QUOTES, 'UTF-8'); ?></td></tr>
            <tr><td><?php echo $is_cn?'日志目录存在':'Log Dir Exists'; ?>:</td><td><b style="color:<?php echo ($health['mmdvm_log_exists']??false)?'#008000':'#ff0000';?>"><?php echo ($health['mmdvm_log_exists']??false)?$yes:$no; ?></b></td></tr>
            <tr><td><?php echo $is_cn?'应用日志目录':'App Log Dir'; ?>:</td><td><?php echo htmlspecialchars($health['app_log_dir']??'', ENT_QUOTES, 'UTF-8'); ?></td></tr>
            <tr><td><?php echo $is_cn?'应用日志可写':'App Log Writable'; ?>:</td><td><b style="color:<?php echo ($health['app_log_writable']??false)?'#008000':'#ff0000';?>"><?php echo ($health['app_log_writable']??false)?$yes:$no; ?></b></td></tr>
            <tr><td><?php echo $is_cn?'配置文件存在':'Config Exists'; ?>:</td><td><b style="color:<?php echo ($health['config_exists']??false)?'#008000':'#ff0000';?>"><?php echo ($health['config_exists']??false)?$yes:$no; ?></b></td></tr>
            <tr><td><?php echo $is_cn?'配置有效':'Config Valid'; ?>:</td><td><b style="color:<?php echo ($health['config_valid']??false)?'#008000':'#ff0000';?>"><?php echo ($health['config_valid']??false)?$yes:$no; ?></b></td></tr>
            <tr><td><?php echo $is_cn?'管理IP':'Admin IP'; ?>:</td><td><?php echo htmlspecialchars($health['ip']??'', ENT_QUOTES, 'UTF-8'); ?></td></tr>
            <tr><td><?php echo $is_cn?'CPU（整机）':'CPU (System)'; ?>:</td><td><?php echo htmlspecialchars($health['cpu_system']??'', ENT_QUOTES, 'UTF-8'); ?></td></tr>
            <tr><td><?php echo $is_cn?'内存占用':'Memory'; ?>:</td><td><?php echo htmlspecialchars($health['mem']??'', ENT_QUOTES, 'UTF-8'); ?></td></tr>
            <tr><td><?php echo $is_cn?'时间':'Time'; ?>:</td><td><?php echo htmlspecialchars($health['time']??date('c'), ENT_QUOTES, 'UTF-8'); ?></td></tr>
            <thead><tr><th colspan="2"><?php echo $lang['conf']; ?></th></tr></thead>
            <tr><td><?php echo $lang['my_call']; ?>:</td><td><input type="text" name="callsign" value="<?php echo htmlspecialchars($config['my_callsign'], ENT_QUOTES, 'UTF-8');?>" /></td></tr>
            <tr><td><?php echo $lang['min_dur']; ?>:</td><td><input type="number" step="0.1" name="min_duration" class="num-box" value="<?php echo htmlspecialchars((string)$config['min_duration'], ENT_QUOTES, 'UTF-8');?>" /></td></tr>
            <tr><td><?php echo $lang['qm_en']; ?>:</td><td><input type="checkbox" name="qm_en" <?php echo ($config['quiet_mode']['enabled']??false)?'checked':'';?> /></td></tr>
            <tr><td><?php echo $lang['qm_range']; ?>:</td><td>
                <input type="time" name="qm_start" class="time-box" value="<?php echo htmlspecialchars($config['quiet_mode']['start']??'23:00', ENT_QUOTES, 'UTF-8');?>" /> - 
                <input type="time" name="qm_end" class="time-box" value="<?php echo htmlspecialchars($config['quiet_mode']['end']??'07:00', ENT_QUOTES, 'UTF-8');?>" />
            </td></tr>
            <thead><tr><th colspan="2"><?php echo $lang['boot_set']; ?></th></tr></thead>
            <tr><td><?php echo $lang['en_boot']; ?>:</td><td><input type="checkbox" name="boot_en" <?php echo ($config['boot_push_enabled']??true)?'checked':'';?> /></td></tr>
            <thead><tr><th colspan="2"><?php echo $lang['temp_set']; ?></th></tr></thead>
            <tr><td><?php echo $lang['en_temp']; ?>:</td><td><input type="checkbox" name="temp_en" <?php echo ($config['temp_alert_enabled']??false)?'checked':'';?> /></td></tr>
            <tr><td><?php echo $lang['th_temp']; ?>:</td><td>
                <input type="number" step="0.1" name="temp_th" class="num-box" value="<?php echo htmlspecialchars((string)($config['temp_threshold']??65.0), ENT_QUOTES, 'UTF-8');?>" />
                <select name="temp_unit">
                    <option value="C" <?php echo ($config['temp_unit']??'C')=='C'?'selected':'';?>>°C</option>
                    <option value="F" <?php echo ($config['temp_unit']??'C')=='F'?'selected':'';?>>°F</option>
                </select>
            </td></tr>
            <tr><td><?php echo $lang['int_temp']; ?>:</td><td><input type="number" name="temp_int" class="num-box" value="<?php echo htmlspecialchars((string)($config['temp_interval']??30), ENT_QUOTES, 'UTF-8');?>" /></td></tr>
            <tr><td colspan="2" style="padding-left:10px; color:#555; font-size:12px;">
                <?php 
                    $unit = htmlspecialchars($config['temp_unit']??'C', ENT_QUOTES, 'UTF-8'); 
                    $interval = intval($config['temp_interval']??30);
                    echo $is_cn 
                        ? "提示：温度达到或超过阈值时触发预警；发送间隔为 {$interval} 分钟；当前单位 {$unit}" 
                        : "Hint: Alert triggers when temperature ≥ threshold; interval {$interval} min; unit {$unit}";
                ?>
            </td></tr>
            <thead><tr><th colspan="2"><?php echo $lang['tg_set']; ?></th></tr></thead>
            <tr><td><?php echo $lang['en']; ?>:</td><td><input type="checkbox" name="tg_en" <?php echo ($config['push_tg_enabled']??false)?'checked':'';?> /></td></tr>
            <tr><td>Token:</td><td><input type="password" name="tg_token" value="<?php echo htmlspecialchars($config['tg_token']??'', ENT_QUOTES, 'UTF-8');?>" /></td></tr>
            <tr><td>Chat ID:</td><td><input type="text" name="tg_chat_id" value="<?php echo htmlspecialchars($config['tg_chat_id']??'', ENT_QUOTES, 'UTF-8');?>" /></td></tr>
            <thead><tr><th colspan="2"><?php echo $lang['wx_set']; ?></th></tr></thead>
            <tr><td><?php echo $lang['en']; ?>:</td><td><input type="checkbox" name="wx_en" <?php echo ($config['push_wx_enabled']??false)?'checked':'';?> /></td></tr>
            <tr><td>Token:</td><td><input type="password" name="wx_token" value="<?php echo htmlspecialchars($config['wx_token']??'', ENT_QUOTES, 'UTF-8');?>" /></td></tr>
            <thead><tr><th colspan="2"><?php echo $lang['fs_set']; ?></th></tr></thead>
            <tr><td><?php echo $lang['en']; ?>:</td><td><input type="checkbox" name="fs_en" <?php echo ($config['push_fs_enabled']??false)?'checked':'';?> /></td></tr>
            <tr><td>Webhook:</td><td><input type="text" name="fs_webhook" value="<?php echo htmlspecialchars($config['fs_webhook']??'', ENT_QUOTES, 'UTF-8');?>" /></td></tr>
            <tr><td>Secret:</td><td><input type="password" name="fs_secret" value="<?php echo htmlspecialchars($config['fs_secret']??'', ENT_QUOTES, 'UTF-8');?>" /></td></tr>
            <thead><tr><th colspan="2"><?php echo $lang['ign_list']; ?></th></tr></thead>
            <tr><td colspan="2" align="center"><textarea name="ignore_list" placeholder="<?php echo $lang['list_hint'];?>"><?php echo htmlspecialchars(format_list_for_web($config['ignore_list']??''), ENT_QUOTES, 'UTF-8');?></textarea></td></tr>
            <thead><tr><th colspan="2"><?php echo $lang['foc_list']; ?></th></tr></thead>
            <tr><td colspan="2" align="center"><textarea name="focus_list" placeholder="<?php echo $lang['list_hint'];?>"><?php echo htmlspecialchars(format_list_for_web($config['focus_list']??''), ENT_QUOTES, 'UTF-8');?></textarea></td></tr>
            <tr><td colspan="2" style="text-align: center !important; padding: 25px 0;">
                <button type="submit" name="action" value="save" style="width:130px; height:34px; font-weight:bold;"><?php echo $lang['btn_save']; ?></button>
                <button type="submit" name="action" value="test" class="btn-test" style="width:130px; height:34px; margin-left: 30px;"><?php echo $lang['btn_test']; ?></button>
            </td></tr>
        </table></form>
    </div>
    <div class="footer">Pi-Star / Pi-Star Dashboard <?php echo $version; ?>, Mod by BA4SMQ.</div>
</div>
</body></html>
