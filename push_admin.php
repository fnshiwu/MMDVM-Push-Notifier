<?php
/**
 * MMDVM-Push-Notifier - Pi-Star Web Admin
 * Compatible with Pi-Star 4.2.x (Bullseye) and 4.3.x (Bookworm, PHP 8.2+)
 * 兼容 Pi-Star 4.2.x / 4.3.x，PHP 8.1 - 8.4 无弃用告警
 */
session_start();

$configFile    = '/etc/mmdvm_push.json';
$serviceName   = 'mmdvm_push.service';
$scriptPath    = '/home/pi-star/MMDVM-Push-Notifier/mmdvm_push.py';
$updateScript  = '/home/pi-star/MMDVM-Push-Notifier/update.sh';
$selfUrl       = '/admin/' . basename(__FILE__);

// =========================
// Language detection | 语言检测
// =========================
$accept = $_SERVER['HTTP_ACCEPT_LANGUAGE'] ?? '';
$detected_lang = (stripos($accept, 'zh') !== false) ? 'cn' : 'en';

// =========================
// Environment detection | 环境检测
// =========================
$pistar_version = 'unknown';
if (is_readable('/etc/pistar-release')) {
    $release = (string)@file_get_contents('/etc/pistar-release');
    if (preg_match('/Version=([0-9][0-9.]*)/', $release, $m)) {
        $pistar_version = $m[1];
    }
}

$debian_version = 'unknown';
if (is_readable('/etc/debian_version')) {
    $debian_version = trim((string)@file_get_contents('/etc/debian_version'));
}
$debian_major = (int)explode('.', $debian_version)[0];
$os_label = 'Debian ' . $debian_version;
if ($debian_major === 12) {
    $os_label .= ' (Bookworm)';
} elseif ($debian_major === 13) {
    $os_label .= ' (Trixie)';
} elseif ($debian_major === 11) {
    $os_label .= ' (Bullseye)';
}

$python_version = trim((string)@shell_exec('python3 --version 2>/dev/null'));
$php_version    = PHP_VERSION;

// Version of the notifier | 推送程序版本
$version_raw = @shell_exec('python3 ' . escapeshellarg($scriptPath) . ' --version 2>/dev/null');
$version = trim((string)$version_raw);
if ($version === '') {
    $version = 'unknown';
}

// =========================
// Disk read/write control | 磁盘读写控制
// =========================
function set_disk(string $mode): void
{
    foreach (["/usr/local/sbin/rpi-$mode", "/usr/local/bin/rpi-$mode", "/usr/bin/rpi-$mode"] as $path) {
        if (file_exists($path)) {
            @shell_exec('sudo ' . escapeshellarg($path) . ' 2>/dev/null');
            break;
        }
    }
    @shell_exec("sudo mount -o remount,$mode / 2>/dev/null");
}

// Clean quotes/spaces out of tokens | 清洗 Token 首尾符号
function clean_input_token($val): string
{
    return trim((string)$val, " \t\n\r\0\x0B\"'");
}

// =========================
// Config bootstrap | 配置初始化
// =========================
if (!file_exists($configFile)) {
    set_disk('rw');
    @file_put_contents($configFile, json_encode([
        "my_callsign" => "",
        "min_duration" => 5.0,
        "ui_lang" => $detected_lang,
        "ignore_list" => "",
        "focus_list" => "",
        "log_dir" => ""
    ], 448));
    @chgrp($configFile, 'www-data');
    @chmod($configFile, 0664);
    set_disk('ro');
}

$configRaw = @file_get_contents($configFile);
$config = json_decode((string)$configRaw, true);
if (!is_array($config)) {
    $config = [];
    $configError = true;
}
if (!isset($config['ui_lang']) || $config['ui_lang'] === '') {
    set_disk('rw');
    $config['ui_lang'] = $detected_lang;
    @file_put_contents($configFile, json_encode($config, 448));
    set_disk('ro');
}

$csrfToken = $_SESSION['csrf_token'] ?? bin2hex(random_bytes(32));
$_SESSION['csrf_token'] = $csrfToken;

// =========================
// POST handlers | 表单处理
// =========================
if ($_SERVER['REQUEST_METHOD'] === 'POST' || isset($_GET['set_lang'])) {
    set_disk('rw');

    $current_ui_lang = $_SESSION['pistar_push_lang'] ?? ($config['ui_lang'] ?? 'cn');
    $valid_csrf = true;
    if ($_SERVER['REQUEST_METHOD'] === 'POST' && !isset($_GET['set_lang'])) {
        $valid_csrf = isset($_POST['csrf_token'])
            && hash_equals($_SESSION['csrf_token'] ?? '', (string)$_POST['csrf_token']);
    }
    $msg = null;

    if (isset($_GET['set_lang'])) {
        $lang_in = ($_GET['set_lang'] === 'en') ? 'en' : 'cn';
        $config['ui_lang'] = $lang_in;
        $_SESSION['pistar_push_lang'] = $lang_in;
        @file_put_contents($configFile, json_encode($config, 448));
    } elseif (isset($_POST['action']) && $_POST['action'] === 'save' && $valid_csrf) {
        $newConfig = [
            "my_callsign"        => strtoupper(trim((string)($_POST['callsign'] ?? ''))),
            "min_duration"       => floatval($_POST['min_duration'] ?? 5.0),
            "quiet_mode"         => [
                "enabled" => isset($_POST['qm_en']),
                "start"   => preg_match('/^\d{2}:\d{2}$/', $_POST['qm_start'] ?? '') ? $_POST['qm_start'] : '23:00',
                "end"     => preg_match('/^\d{2}:\d{2}$/', $_POST['qm_end'] ?? '') ? $_POST['qm_end'] : '07:00',
            ],
            "boot_push_enabled"  => isset($_POST['boot_en']),
            "temp_alert_enabled" => isset($_POST['temp_en']),
            "temp_threshold"     => floatval($_POST['temp_th'] ?? 65.0),
            "temp_interval"      => max(1, intval($_POST['temp_int'] ?? 30)),
            "temp_unit"          => (($_POST['temp_unit'] ?? 'C') === 'F') ? 'F' : 'C',
            "push_tg_enabled"    => isset($_POST['tg_en']),
            "tg_token"           => clean_input_token($_POST['tg_token'] ?? ''),
            "tg_chat_id"         => clean_input_token($_POST['tg_chat_id'] ?? ''),
            "push_wx_enabled"    => isset($_POST['wx_en']),
            "wx_token"           => clean_input_token($_POST['wx_token'] ?? ''),
            "push_fs_enabled"    => isset($_POST['fs_en']),
            "fs_webhook"         => clean_input_token($_POST['fs_webhook'] ?? ''),
            "fs_secret"          => clean_input_token($_POST['fs_secret'] ?? ''),
            "ignore_list"        => trim((string)($_POST['ignore_list'] ?? '')),
            "focus_list"         => trim((string)($_POST['focus_list'] ?? '')),
            "log_dir"            => trim((string)($_POST['log_dir'] ?? '')),
            "dedup_window"       => floatval($_POST['dedup_window'] ?? 3),
            "ui_lang"            => $current_ui_lang,
        ];
        $writeRes = @file_put_contents($configFile, json_encode($newConfig, 448));
        if ($writeRes !== false) {
            $config = $newConfig;
            $msg = ($current_ui_lang === 'cn') ? "✅ 设置已保存！" : "✅ Settings Saved!";
        } else {
            $msg = ($current_ui_lang === 'cn')
                ? "❌ 保存失败：磁盘只读或权限不足（可尝试 sudo rpi-rw）"
                : "❌ Save failed: read-only filesystem or permission denied (try sudo rpi-rw).";
        }
    } elseif (isset($_POST['action']) && $_POST['action'] === 'update' && $valid_csrf) {
        @exec('sudo ' . escapeshellarg($updateScript) . ' > /tmp/mmdvm_push_update.log 2>&1 &');
        $msg = ($current_ui_lang === 'cn')
            ? "🚀 更新已在后台进行，约 1 分钟后刷新本页查看版本"
            : "🚀 Update started in background, refresh in about a minute.";
    } elseif (isset($_POST['action']) && !$valid_csrf) {
        $msg = ($current_ui_lang === 'cn') ? "❌ CSRF 校验失败，请刷新页面重试" : "❌ CSRF validation failed, please reload.";
    }

    set_disk('ro');

    // Service control | 服务控制
    $action = (string)($_POST['action'] ?? '');
    if ($valid_csrf && in_array($action, ['start', 'stop', 'restart'], true)) {
        @shell_exec('sudo systemctl ' . $action . ' ' . escapeshellarg($serviceName) . ' 2>&1');
        usleep(700000);
    }

    // Test push | 测试推送
    if ($valid_csrf && $action === 'test') {
        $out = [];
        $res = 0;
        @exec('sudo /usr/bin/python3 ' . escapeshellarg($scriptPath) . ' --test 2>&1', $out, $res);
        $joined = implode("\n", $out);
        $ok = (strpos($joined, 'Success') !== false);
        if ($ok) {
            $msg = ($current_ui_lang === 'cn') ? "✅ 测试推送已发送" : "✅ Test notification sent";
        } else {
            $tail = trim(function_exists('mb_substr') ? mb_substr($joined, -300) : substr($joined, -300));
            $msg = ($current_ui_lang === 'cn')
                ? "❌ 测试失败：" . ($tail !== '' ? $tail : "请查看 /var/log/pi-star/mmdvm_push.log")
                : "❌ Test failed: " . ($tail !== '' ? $tail : "see /var/log/pi-star/mmdvm_push.log");
        }
    }

    if ($msg !== null) {
        $_SESSION['alert_msg'] = $msg;
    }
    header('Location: ' . $selfUrl);
    exit;
}

if (isset($_SESSION['alert_msg'])) {
    $alertMsg = $_SESSION['alert_msg'];
    unset($_SESSION['alert_msg']);
}

function format_list_for_web($data): string
{
    if (is_array($data)) {
        return implode("; ", $data);
    }
    return (string)$data;
}

$current_lang = $_SESSION['pistar_push_lang'] ?? ($config['ui_lang'] ?? 'cn');
$is_cn = ($current_lang !== 'en');

// =========================
// Service status | 服务状态
// =========================
$svc_state = trim((string)@shell_exec('sudo systemctl is-active ' . escapeshellarg($serviceName) . ' 2>/dev/null'));
$svc_enabled = trim((string)@shell_exec('sudo systemctl is-enabled ' . escapeshellarg($serviceName) . ' 2>/dev/null'));
$is_running = ($svc_state === 'active');
$svc_state = ($svc_state !== '') ? $svc_state : 'unknown';

// =========================
// Health check | 健康检查
// =========================
$healthRaw = (string)@shell_exec('python3 ' . escapeshellarg($scriptPath) . ' --health 2>/dev/null');
$health = null;
if ($healthRaw !== '') {
    $start = strpos($healthRaw, '{');
    $end = strrpos($healthRaw, '}');
    if ($start !== false && $end !== false && $end > $start) {
        $health = json_decode(substr($healthRaw, $start, $end - $start + 1), true);
    }
}
if (!is_array($health)) {
    $health = [
        "version" => $version,
        "pistar_version" => $pistar_version,
        "debian_version" => $debian_version,
        "python_version" => $python_version,
        "app_log_dir" => "",
        "app_log_writable" => false,
        "log_dir" => "/var/log/pi-star",
        "mmdvm_log_dir" => "/var/log/pi-star",
        "mmdvm_log_exists" => is_dir('/var/log/pi-star'),
        "mmdvm_log_readable" => is_readable('/var/log/pi-star'),
        "current_log" => "",
        "current_log_readable" => false,
        "service_user" => "",
        "config_exists" => file_exists($configFile),
        "config_valid" => is_array($config) && count($config) > 0,
        "parser_selftest" => false,
        "time" => date('c')
    ];
}

// Tail of notifier log for quick diagnosis | 快速诊断用的日志尾部
// Path comes from --health because the service may fall back to /tmp
$appLogDir  = rtrim((string)($health['app_log_dir'] ?? ''), "/\\");
$appLogFile = ($appLogDir !== '' ? $appLogDir : '/var/log/pi-star') . '/mmdvm_push.log';
$logTail = '';
if (is_readable($appLogFile)) {
    $lines = @file($appLogFile, FILE_IGNORE_NEW_LINES);
    if (is_array($lines)) {
        $logTail = implode("\n", array_slice($lines, -40));
    }
}

$yes = $is_cn ? '是' : 'Yes';
$no  = $is_cn ? '否' : 'No';
$hostname = gethostname() ?: 'unknown';

$lang = [
    'cn' => [
        'nav_dash' => '仪表盘', 'nav_admin' => '管理', 'nav_power' => '电源', 'nav_push' => '推送设置',
        'srv_ctrl' => '服务控制', 'status' => '状态', 'run' => '运行中', 'stop' => '已停止',
        'btn_start' => '启动', 'btn_stop' => '停止', 'btn_res' => '重启', 'btn_test' => '发送测试',
        'btn_save' => '保存设置', 'btn_update' => '检查更新', 'conf' => '推送功能设置',
        'my_call' => '我的呼号', 'min_dur' => '最小推送时长 (秒)', 'qm_en' => '开启静音时段',
        'qm_range' => '静音时间范围',
        'boot_set' => '启动通知', 'temp_set' => '高温预警', 'en_boot' => '设备启动提醒',
        'en_temp' => '高温预警', 'th_temp' => '预警阈值', 'int_temp' => '预警间隔 (分)',
        'tg_set' => 'Telegram 设置', 'wx_set' => '微信 (PushPlus) 设置', 'fs_set' => '飞书 (Feishu) 设置',
        'en' => '启用推送', 'ign_list' => '忽略列表 (黑名单)', 'foc_list' => '关注列表 (白名单)',
        'list_hint' => '仅呼号，使用"；"或逗号分隔'
    ],
    'en' => [
        'nav_dash' => 'Dashboard', 'nav_admin' => 'Admin', 'nav_power' => 'Power', 'nav_push' => 'Push Settings',
        'srv_ctrl' => 'Service Control', 'status' => 'Status', 'run' => 'RUNNING', 'stop' => 'STOPPED',
        'btn_start' => 'Start', 'btn_stop' => 'Stop', 'btn_res' => 'Restart', 'btn_test' => 'Send Test',
        'btn_save' => 'SAVE SETTINGS', 'btn_update' => 'Update Now', 'conf' => 'Push Notifier Settings',
        'my_call' => 'My Callsign', 'min_dur' => 'Min Duration (sec)', 'qm_en' => 'Quiet Mode',
        'qm_range' => 'Quiet Time Range (HH:mm)',
        'boot_set' => 'Boot Notice', 'temp_set' => 'Temp Alert', 'en_boot' => 'Enable Boot Push',
        'en_temp' => 'Enable Temp Alert', 'th_temp' => 'Threshold', 'int_temp' => 'Interval (min)',
        'tg_set' => 'Telegram Settings', 'wx_set' => 'WeChat (PushPlus) Settings', 'fs_set' => 'Feishu Settings',
        'en' => 'Enable', 'ign_list' => 'Ignore List', 'foc_list' => 'Focus List',
        'list_hint' => 'Callsigns only; separated by ";" or comma'
    ]
][$is_cn ? 'cn' : 'en'];

function h($s): string
{
    return htmlspecialchars((string)$s, ENT_QUOTES, 'UTF-8');
}

function badge(bool $ok, string $yes, string $no): string
{
    $color = $ok ? '#0a0' : '#c00';
    return '<b style="color:' . $color . '">' . h($ok ? $yes : $no) . '</b>';
}
?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" lang="<?php echo $is_cn ? 'zh-CN' : 'en'; ?>">
<head>
    <meta http-equiv="Content-Type" content="text/html; charset=utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <link rel="stylesheet" type="text/css" href="css/pistar-css.php" />
    <title>Push Notifier <?php echo h($version); ?></title>
    <style type="text/css">
        textarea { width: 95%; height: 55px; font-family: monospace; font-size: 12px; }
        input[type="text"], input[type="password"] { width: 95%; height: 22px; }
        input[type="number"], input[type="time"] { height: 22px; }
        select { height: 24px; vertical-align: middle; }
        .time-box { width: 80px !important; }
        .num-box { width: 70px !important; }
        .btn-test { background: #b55; color: #fff; font-weight: bold; border: 1px solid #000; cursor: pointer; }
        .btn-update { background: #444; color: #fff; border: 1px solid #000; cursor: pointer; padding: 2px 10px; margin-left: 15px; }
        table.settings td:first-child { font-weight: bold; text-align: left !important; padding-left: 10px; width: 38%; }
        table.settings td:last-child { text-align: left !important; padding-left: 10px; word-break: break-all; }
        .version-info { font-size: 11px; color: #ccc; text-align: right; padding-right: 10px; }
        .logbox { background: #111; color: #9f9; font-family: monospace; font-size: 11px; padding: 8px;
                  white-space: pre-wrap; max-height: 260px; overflow: auto; border: 1px solid #444; }
        .alertbox { background: #ffffc0; color: #000; padding: 5px; text-align: center; border: 1px solid #666; }
    </style>
</head>
<body>
<div class="container">
    <div class="header">
        <div style="font-size: 8px; text-align: left; padding-left: 8px; float: left;">Hostname: <?php echo h($hostname); ?></div>
        <h1>Pi-Star Push Notifier (<?php echo h($version); ?>)</h1>
        <p style="text-align: right; padding-right: 10px; color: #fff;">
            <a href="/" style="color: #fff;"><?php echo h($lang['nav_dash']); ?></a> |
            <a href="/admin/" style="color: #fff;"><?php echo h($lang['nav_admin']); ?></a> |
            <a href="/admin/power.php" style="color: #fff;"><?php echo h($lang['nav_power']); ?></a> |
            <a href="<?php echo h($selfUrl); ?>" style="color: #fff; font-weight: bold;"><?php echo h($lang['nav_push']); ?></a> |
            <a href="?set_lang=<?php echo $is_cn ? 'en' : 'cn'; ?>" style="color: #ffff00;">[<?php echo $is_cn ? 'English' : '中文'; ?>]</a>
        </p>
        <div class="version-info">Pi-Star <?php echo h($pistar_version); ?> | <?php echo h($os_label); ?></div>
    </div>
    <div class="contentwide">
        <?php if (isset($alertMsg)): ?>
            <div class="alertbox"><b><?php echo h($alertMsg); ?></b></div>
        <?php endif; ?>
        <?php if (!empty($configError)): ?>
            <div class="alertbox"><b>⚠️ <?php echo $is_cn ? '配置文件 JSON 解析失败，请检查语法' : 'Config JSON is invalid, please check the syntax'; ?></b></div>
        <?php endif; ?>

        <form method="post">
        <input type="hidden" name="csrf_token" value="<?php echo h($csrfToken); ?>" />
        <table class="settings">
            <thead><tr><th colspan="2"><?php echo h($lang['srv_ctrl']); ?></th></tr></thead>
            <tr><td><?php echo h($lang['status']); ?>:</td><td>
                <b style="color:<?php echo $is_running ? '#0a0' : '#c00'; ?>"><?php echo h($is_running ? $lang['run'] : $lang['stop']); ?></b>
                <span style="color:#888; font-size:11px;">(<?php echo h($svc_state); ?><?php echo $svc_enabled !== '' ? ' / ' . h($svc_enabled) : ''; ?>)</span>
                <button type="submit" name="action" value="update" class="btn-update"><?php echo h($lang['btn_update']); ?></button>
            </td></tr>
            <tr><td>Action:</td><td>
                <button type="submit" name="action" value="start"><?php echo h($lang['btn_start']); ?></button>
                <button type="submit" name="action" value="stop"><?php echo h($lang['btn_stop']); ?></button>
                <button type="submit" name="action" value="restart"><?php echo h($lang['btn_res']); ?></button>
            </td></tr>

            <thead><tr><th colspan="2"><?php echo $is_cn ? '运行环境 / 健康状态' : 'Environment / Health'; ?></th></tr></thead>
            <tr><td><?php echo $is_cn ? '推送程序版本' : 'Notifier Version'; ?>:</td><td><?php echo h($health['version'] ?? $version); ?></td></tr>
            <tr><td><?php echo $is_cn ? 'Pi-Star 版本' : 'Pi-Star Version'; ?>:</td><td><?php echo h($pistar_version); ?></td></tr>
            <tr><td><?php echo $is_cn ? '系统版本' : 'OS'; ?>:</td><td><?php echo h($os_label); ?></td></tr>
            <tr><td>Python / PHP:</td><td><?php echo h($python_version !== '' ? $python_version : 'unknown'); ?> / <?php echo h($php_version); ?></td></tr>
            <tr><td><?php echo $is_cn ? '服务运行用户' : 'Service User'; ?>:</td><td><?php echo h($health['service_user'] ?? ''); ?></td></tr>
            <tr><td><?php echo $is_cn ? 'MMDVM 日志目录' : 'MMDVM Log Dir'; ?>:</td><td><?php echo h($health['log_dir'] ?? $health['mmdvm_log_dir'] ?? ''); ?></td></tr>
            <tr><td><?php echo $is_cn ? '日志目录可读' : 'Log Dir Readable'; ?>:</td><td><?php echo badge((bool)($health['mmdvm_log_readable'] ?? $health['mmdvm_log_exists'] ?? false), $yes, $no); ?></td></tr>
            <tr><td><?php echo $is_cn ? '当前跟踪日志' : 'Current Log'; ?>:</td><td><?php echo h($health['current_log'] ?? ''); ?></td></tr>
            <tr><td><?php echo $is_cn ? '日志文件可读' : 'Log File Readable'; ?>:</td><td><?php echo badge((bool)($health['current_log_readable'] ?? false), $yes, $no); ?></td></tr>
            <tr><td><?php echo $is_cn ? '应用日志可写' : 'App Log Writable'; ?>:</td><td><?php echo badge((bool)($health['app_log_writable'] ?? false), $yes, $no); ?></td></tr>
            <tr><td><?php echo $is_cn ? '解析器自检' : 'Parser Self-test'; ?>:</td><td><?php echo badge((bool)($health['parser_selftest'] ?? false), $yes, $no); ?></td></tr>
            <tr><td><?php echo $is_cn ? '配置文件存在' : 'Config Exists'; ?>:</td><td><?php echo badge((bool)($health['config_exists'] ?? false), $yes, $no); ?></td></tr>
            <tr><td><?php echo $is_cn ? '管理IP' : 'Admin IP'; ?>:</td><td><?php echo h($health['ip'] ?? ''); ?></td></tr>
            <tr><td><?php echo $is_cn ? 'CPU（整机 / 进程）' : 'CPU (System / Process)'; ?>:</td><td><?php echo h($health['cpu_system'] ?? ''); ?> / <?php echo h($health['cpu_process'] ?? ''); ?></td></tr>
            <tr><td><?php echo $is_cn ? '内存占用' : 'Memory'; ?>:</td><td><?php echo h($health['mem'] ?? ''); ?> (RSS <?php echo h($health['mem_rss_kb'] ?? '0'); ?> KB)</td></tr>
            <tr><td><?php echo $is_cn ? '时间' : 'Time'; ?>:</td><td><?php echo h($health['time'] ?? date('c')); ?></td></tr>

            <thead><tr><th colspan="2"><?php echo h($lang['conf']); ?></th></tr></thead>
            <tr><td><?php echo h($lang['my_call']); ?>:</td><td><input type="text" name="callsign" value="<?php echo h($config['my_callsign'] ?? ''); ?>" /></td></tr>
            <tr><td><?php echo h($lang['min_dur']); ?>:</td><td><input type="number" step="0.1" name="min_duration" class="num-box" value="<?php echo h($config['min_duration'] ?? 5.0); ?>" /></td></tr>
            <tr><td><?php echo $is_cn ? '重复抑制窗口 (秒)' : 'Dedup Window (sec)'; ?>:</td><td><input type="number" step="0.5" name="dedup_window" class="num-box" value="<?php echo h($config['dedup_window'] ?? 3); ?>" /></td></tr>
            <tr><td><?php echo h($lang['qm_en']); ?>:</td><td><input type="checkbox" name="qm_en" <?php echo (!empty($config['quiet_mode']['enabled'])) ? 'checked' : ''; ?> /></td></tr>
            <tr><td><?php echo h($lang['qm_range']); ?>:</td><td>
                <input type="time" name="qm_start" class="time-box" value="<?php echo h($config['quiet_mode']['start'] ?? '23:00'); ?>" /> -
                <input type="time" name="qm_end" class="time-box" value="<?php echo h($config['quiet_mode']['end'] ?? '07:00'); ?>" />
            </td></tr>

            <thead><tr><th colspan="2"><?php echo h($lang['boot_set']); ?></th></tr></thead>
            <tr><td><?php echo h($lang['en_boot']); ?>:</td><td><input type="checkbox" name="boot_en" <?php echo ($config['boot_push_enabled'] ?? true) ? 'checked' : ''; ?> /></td></tr>

            <thead><tr><th colspan="2"><?php echo h($lang['temp_set']); ?></th></tr></thead>
            <tr><td><?php echo h($lang['en_temp']); ?>:</td><td><input type="checkbox" name="temp_en" <?php echo (!empty($config['temp_alert_enabled'])) ? 'checked' : ''; ?> /></td></tr>
            <tr><td><?php echo h($lang['th_temp']); ?>:</td><td>
                <input type="number" step="0.1" name="temp_th" class="num-box" value="<?php echo h($config['temp_threshold'] ?? 65.0); ?>" />
                <select name="temp_unit">
                    <option value="C" <?php echo (($config['temp_unit'] ?? 'C') === 'C') ? 'selected' : ''; ?>>°C</option>
                    <option value="F" <?php echo (($config['temp_unit'] ?? 'C') === 'F') ? 'selected' : ''; ?>>°F</option>
                </select>
            </td></tr>
            <tr><td><?php echo h($lang['int_temp']); ?>:</td><td><input type="number" name="temp_int" class="num-box" value="<?php echo h($config['temp_interval'] ?? 30); ?>" /></td></tr>

            <thead><tr><th colspan="2"><?php echo h($lang['tg_set']); ?></th></tr></thead>
            <tr><td><?php echo h($lang['en']); ?>:</td><td><input type="checkbox" name="tg_en" <?php echo (!empty($config['push_tg_enabled'])) ? 'checked' : ''; ?> /></td></tr>
            <tr><td>Token:</td><td><input type="password" name="tg_token" value="<?php echo h($config['tg_token'] ?? ''); ?>" autocomplete="new-password" /></td></tr>
            <tr><td>Chat ID:</td><td><input type="text" name="tg_chat_id" value="<?php echo h($config['tg_chat_id'] ?? ''); ?>" /></td></tr>

            <thead><tr><th colspan="2"><?php echo h($lang['wx_set']); ?></th></tr></thead>
            <tr><td><?php echo h($lang['en']); ?>:</td><td><input type="checkbox" name="wx_en" <?php echo (!empty($config['push_wx_enabled'])) ? 'checked' : ''; ?> /></td></tr>
            <tr><td>Token:</td><td><input type="password" name="wx_token" value="<?php echo h($config['wx_token'] ?? ''); ?>" autocomplete="new-password" /></td></tr>

            <thead><tr><th colspan="2"><?php echo h($lang['fs_set']); ?></th></tr></thead>
            <tr><td><?php echo h($lang['en']); ?>:</td><td><input type="checkbox" name="fs_en" <?php echo (!empty($config['push_fs_enabled'])) ? 'checked' : ''; ?> /></td></tr>
            <tr><td>Webhook:</td><td><input type="text" name="fs_webhook" value="<?php echo h($config['fs_webhook'] ?? ''); ?>" /></td></tr>
            <tr><td>Secret:</td><td><input type="password" name="fs_secret" value="<?php echo h($config['fs_secret'] ?? ''); ?>" autocomplete="new-password" /></td></tr>

            <thead><tr><th colspan="2"><?php echo h($lang['ign_list']); ?></th></tr></thead>
            <tr><td colspan="2" align="center"><textarea name="ignore_list" placeholder="<?php echo h($lang['list_hint']); ?>"><?php echo h(format_list_for_web($config['ignore_list'] ?? '')); ?></textarea></td></tr>

            <thead><tr><th colspan="2"><?php echo h($lang['foc_list']); ?></th></tr></thead>
            <tr><td colspan="2" align="center"><textarea name="focus_list" placeholder="<?php echo h($lang['list_hint']); ?>"><?php echo h(format_list_for_web($config['focus_list'] ?? '')); ?></textarea></td></tr>

            <thead><tr><th colspan="2"><?php echo $is_cn ? '高级：日志目录' : 'Advanced: Log Directory'; ?></th></tr></thead>
            <tr><td>log_dir:</td><td>
                <input type="text" name="log_dir" value="<?php echo h($config['log_dir'] ?? ''); ?>" placeholder="/var/log/pi-star" />
                <div style="font-size:11px; color:#888; margin-top:3px;">
                    <?php echo $is_cn ? '留空 = 自动探测（推荐）' : 'Empty = auto detect (recommended)'; ?>
                </div>
            </td></tr>

            <tr><td colspan="2" style="text-align: center !important; padding: 25px 0;">
                <button type="submit" name="action" value="save" style="width:140px; height:34px; font-weight:bold;"><?php echo h($lang['btn_save']); ?></button>
                <button type="submit" name="action" value="test" class="btn-test" style="width:140px; height:34px; margin-left: 30px;"><?php echo h($lang['btn_test']); ?></button>
            </td></tr>
        </table>
        </form>

        <?php if ($logTail !== ''): ?>
        <details style="margin-top:10px;">
            <summary style="cursor:pointer;"><?php echo $is_cn ? '最近运行日志（最后 40 行）' : 'Recent log (last 40 lines)'; ?></summary>
            <div class="logbox"><?php echo h($logTail); ?></div>
        </details>
        <?php endif; ?>
    </div>
    <div class="footer">Pi-Star Dashboard | MMDVM-Push-Notifier <?php echo h($version); ?> | Mod by BA4SMQ</div>
</div>
</body>
</html>
