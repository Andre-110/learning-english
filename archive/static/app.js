// 应用配置
const CONFIG = {
    // 获取基础路径（支持子路径部署，如 /english/）
    basePath: (() => {
        // 获取当前路径，去掉末尾的文件名（如 index.html）
        let path = window.location.pathname;
        // 如果路径以 / 结尾，去掉它
        if (path.endsWith('/')) {
            path = path.slice(0, -1);
        }
        // 如果路径包含 .html，去掉文件名部分
        if (path.includes('.html')) {
            path = path.substring(0, path.lastIndexOf('/'));
        }
        return path || '';
    })(),
    wsUrl: (() => {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const host = window.location.host;
        // 获取基础路径
        let basePath = window.location.pathname;
        if (basePath.endsWith('/')) {
            basePath = basePath.slice(0, -1);
        }
        if (basePath.includes('.html')) {
            basePath = basePath.substring(0, basePath.lastIndexOf('/'));
        }
        return `${protocol}//${host}${basePath}`;
    })(),
    apiUrl: (() => {
        const protocol = window.location.protocol;
        const host = window.location.host;
        // 获取基础路径
        let basePath = window.location.pathname;
        if (basePath.endsWith('/')) {
            basePath = basePath.slice(0, -1);
        }
        if (basePath.includes('.html')) {
            basePath = basePath.substring(0, basePath.lastIndexOf('/'));
        }
        return `${protocol}//${host}${basePath}`;
    })(),
    sampleRate: 16000,
    channels: 1,
    bufferSize: 4096
};

// 应用状态
const state = {
    ws: null,
    conversationId: null,
    userId: null,
    username: null,
    accessToken: null,
    isRecording: false,
    mediaRecorder: null,
    audioChunks: [],
    audioContext: null,
    audioStream: null,
    audioPlayer: null,
    audioQueuePlayer: false,
    historyExpanded: false,
    conversations: [],
    processingMode: 'standard',  // 'standard' 或 'gpt4o-audio'
    streamingMessageId: null     // 当前流式消息的ID
};

// 获取API请求头（包含token）
function getAuthHeaders() {
    const headers = {
        'Content-Type': 'application/json'
    };
    if (state.accessToken) {
        headers['Authorization'] = `Bearer ${state.accessToken}`;
    }
    return headers;
}

// DOM元素
const elements = {
    statusIndicator: document.getElementById('statusIndicator'),
    statusText: document.getElementById('statusText'),
    authSection: document.getElementById('authSection'),
    loginTab: document.getElementById('loginTab'),
    registerTab: document.getElementById('registerTab'),
    loginForm: document.getElementById('loginForm'),
    registerForm: document.getElementById('registerForm'),
    loginUsername: document.getElementById('loginUsername'),
    loginPassword: document.getElementById('loginPassword'),
    registerUsername: document.getElementById('registerUsername'),
    registerEmail: document.getElementById('registerEmail'),
    registerPassword: document.getElementById('registerPassword'),
    registerPasswordConfirm: document.getElementById('registerPasswordConfirm'),
    loginBtn: document.getElementById('loginBtn'),
    registerBtn: document.getElementById('registerBtn'),
    logoutBtn: document.getElementById('logoutBtn'),
    userInfoSection: document.getElementById('userInfoSection'),
    currentUsername: document.getElementById('currentUsername'),
    userStats: document.getElementById('userStats'),
    startBtn: document.getElementById('startBtn'),
    recordBtn: document.getElementById('recordBtn'),
    recordingStatus: document.getElementById('recordingStatus'),
    conversationList: document.getElementById('conversationList'),
    profileContent: document.getElementById('profileContent'),
    assessmentContent: document.getElementById('assessmentContent'),
    audioPlayer: document.getElementById('audioPlayer'),
    clearBtn: document.getElementById('clearBtn'),
    realtimeTranscription: document.getElementById('realtimeTranscription'),
    realtimeTranscriptionText: document.getElementById('realtimeTranscriptionText'),
    performanceTestBtn: document.getElementById('performanceTestBtn'),
    performanceContent: document.getElementById('performanceContent'),
    performanceMetrics: document.getElementById('performanceMetrics'),
    historyHeader: document.getElementById('historyHeader'),
    historyToggle: document.getElementById('historyToggle'),
    historyList: document.getElementById('historyList'),
    processingMode: document.getElementById('processingMode')
};

// 初始化
document.addEventListener('DOMContentLoaded', () => {
    initializeApp();
});

function initializeApp() {
    // 绑定事件
    elements.loginTab?.addEventListener('click', () => switchAuthTab('login'));
    elements.registerTab?.addEventListener('click', () => switchAuthTab('register'));
    elements.loginBtn?.addEventListener('click', handleLogin);
    elements.registerBtn?.addEventListener('click', handleRegister);
    elements.logoutBtn?.addEventListener('click', handleLogout);
    elements.startBtn.addEventListener('click', startConversation);
    elements.recordBtn.addEventListener('click', toggleRecording);
    elements.clearBtn.addEventListener('click', clearConversation);
    elements.performanceTestBtn.addEventListener('click', startPerformanceTest);
    elements.historyHeader?.addEventListener('click', toggleHistoryList);
    
    // 处理模式选择
    elements.processingMode?.addEventListener('change', (e) => {
        state.processingMode = e.target.value;
        console.log('处理模式切换为:', state.processingMode);
        // 如果已连接，需要重新连接到新的端点
        if (state.ws && state.ws.readyState === WebSocket.OPEN) {
            showStatus(`已切换到${state.processingMode === 'gpt4o-audio' ? 'GPT-4o Audio' : '标准'}模式，下次对话生效`, 'info');
        }
    });
    
    // 初始化音频播放器
    state.audioPlayer = elements.audioPlayer;
    
    // 检查浏览器支持
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        showError('您的浏览器不支持录音功能');
        elements.recordBtn.disabled = true;
    }
    
    // 检查是否有保存的token
    const savedToken = localStorage.getItem('accessToken');
    const savedUserId = localStorage.getItem('userId');
    const savedUsername = localStorage.getItem('username');
    
    if (savedToken && savedUserId && savedUsername) {
        state.accessToken = savedToken;
        state.userId = savedUserId;
        state.username = savedUsername;
        // 验证token是否有效
        verifyTokenAndLoadUser();
    }
}

// 切换登录/注册标签
function switchAuthTab(tab) {
    if (tab === 'login') {
        elements.loginTab.classList.add('active');
        elements.registerTab.classList.remove('active');
        elements.loginForm.style.display = 'block';
        elements.registerForm.style.display = 'none';
    } else {
        elements.loginTab.classList.remove('active');
        elements.registerTab.classList.add('active');
        elements.loginForm.style.display = 'none';
        elements.registerForm.style.display = 'block';
    }
}

// 登录处理
async function handleLogin() {
    const username = elements.loginUsername.value.trim();
    const password = elements.loginPassword.value.trim();
    
    if (!username || !password) {
        alert('请输入用户名和密码');
        return;
    }
    
    try {
        const apiUrl = `${CONFIG.apiUrl}/auth/login`;
        const response = await fetch(apiUrl, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                username: username,
                password: password
            })
        });
        
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || '登录失败');
        }
        
        const data = await response.json();
        
        // 保存token和用户信息
        state.accessToken = data.access_token;
        state.userId = data.user_id;
        state.username = data.username;
        
        localStorage.setItem('accessToken', data.access_token);
        localStorage.setItem('userId', data.user_id);
        localStorage.setItem('username', data.username);
        
        // 显示用户信息区域
        elements.authSection.style.display = 'none';
        elements.userInfoSection.style.display = 'block';
        elements.currentUsername.textContent = data.username;
        
        // 加载用户画像
        await loadUserProfile(data.user_id);
        
        // 加载历史对话列表
        await loadConversationHistory(data.user_id);
        
        // 更新状态
        updateStatus('已登录', 'connected');
        
        // 清空表单
        elements.loginUsername.value = '';
        elements.loginPassword.value = '';
        
    } catch (error) {
        console.error('登录失败:', error);
        alert('登录失败: ' + error.message);
    }
}

// 注册处理
async function handleRegister() {
    const username = elements.registerUsername.value.trim();
    const email = elements.registerEmail.value.trim() || null;
    const password = elements.registerPassword.value.trim();
    const passwordConfirm = elements.registerPasswordConfirm.value.trim();
    
    if (!username || username.length < 3) {
        alert('用户名至少需要3个字符');
        return;
    }
    
    if (!password || password.length < 6) {
        alert('密码至少需要6个字符');
        return;
    }
    
    if (password !== passwordConfirm) {
        alert('两次输入的密码不一致');
        return;
    }
    
    try {
        const apiUrl = `${CONFIG.apiUrl}/auth/register`;
        const response = await fetch(apiUrl, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                username: username,
                email: email,
                password: password
            })
        });
        
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || '注册失败');
        }
        
        const data = await response.json();
        
        // 保存token和用户信息
        state.accessToken = data.access_token;
        state.userId = data.user_id;
        state.username = data.username;
        
        localStorage.setItem('accessToken', data.access_token);
        localStorage.setItem('userId', data.user_id);
        localStorage.setItem('username', data.username);
        
        // 显示用户信息区域
        elements.authSection.style.display = 'none';
        elements.userInfoSection.style.display = 'block';
        elements.currentUsername.textContent = data.username;
        
        // 加载用户画像
        await loadUserProfile(data.user_id);
        
        // 加载历史对话列表
        await loadConversationHistory(data.user_id);
        
        // 更新状态
        updateStatus('注册成功，已登录', 'connected');
        
        // 清空表单
        elements.registerUsername.value = '';
        elements.registerEmail.value = '';
        elements.registerPassword.value = '';
        elements.registerPasswordConfirm.value = '';
        
        // 切换到登录标签
        switchAuthTab('login');
        
    } catch (error) {
        console.error('注册失败:', error);
        alert('注册失败: ' + error.message);
    }
}

// 验证token并加载用户信息
async function verifyTokenAndLoadUser() {
    try {
        const apiUrl = `${CONFIG.apiUrl}/auth/me`;
        const response = await fetch(apiUrl, {
            headers: getAuthHeaders()
        });
        
        if (!response.ok) {
            // Token无效，清除保存的信息
            handleLogout();
            return;
        }
        
        const userInfo = await response.json();
        
        // 显示用户信息区域
        elements.authSection.style.display = 'none';
        elements.userInfoSection.style.display = 'block';
        elements.currentUsername.textContent = userInfo.username;
        
        // 加载用户画像
        await loadUserProfile(state.userId);
        
        // 加载历史对话列表
        await loadConversationHistory(state.userId);
        
        // 更新状态
        updateStatus('已登录', 'connected');
        
    } catch (error) {
        console.error('验证token失败:', error);
        handleLogout();
    }
}

// 退出登录
async function handleLogout() {
    // 调用登出API（可选）
    if (state.accessToken) {
        try {
            const apiUrl = `${CONFIG.apiUrl}/auth/logout`;
            await fetch(apiUrl, {
                method: 'POST',
                headers: getAuthHeaders()
            });
        } catch (error) {
            console.error('登出API调用失败:', error);
        }
    }
    
    // 清除状态
    state.userId = null;
    state.username = null;
    state.accessToken = null;
    state.conversationId = null;
    state.conversations = [];
    
    // 清除localStorage
    localStorage.removeItem('accessToken');
    localStorage.removeItem('userId');
    localStorage.removeItem('username');
    
    // 关闭WebSocket连接
    if (state.ws) {
        state.ws.close();
        state.ws = null;
    }
    
    // 显示登录区域
    elements.authSection.style.display = 'block';
    elements.userInfoSection.style.display = 'none';
    
    // 清空对话列表
    elements.conversationList.innerHTML = '<div class="empty-state"><p>对话将在这里显示</p></div>';
    elements.historyList.innerHTML = '<div class="empty-state"><p>暂无历史对话</p></div>';
    
    // 重置状态
    updateStatus('未连接', 'disconnected');
    elements.recordBtn.disabled = true;
    
    // 切换到登录标签
    switchAuthTab('login');
}

// 加载用户画像
async function loadUserProfile(userId) {
    try {
        const apiUrl = `${CONFIG.apiUrl}/users/${userId}/profile`;
        const response = await fetch(apiUrl, {
            headers: getAuthHeaders()
        });
        
        if (!response.ok) {
            throw new Error(`获取用户画像失败: ${response.status}`);
        }
        
        const profile = await response.json();
        
        // 更新用户统计信息
        const statsHtml = `
            <div class="stat-item">
                <span class="stat-label">综合分数:</span>
                <span class="stat-value">${profile.overall_score?.toFixed(1) || 0}/100</span>
            </div>
            <div class="stat-item">
                <span class="stat-label">CEFR等级:</span>
                <span class="stat-value">${profile.cefr_level || 'A1'}</span>
            </div>
            <div class="stat-item">
                <span class="stat-label">对话轮数:</span>
                <span class="stat-value">${profile.conversation_count || 0}</span>
            </div>
        `;
        elements.userStats.innerHTML = statsHtml;
        
        // 更新用户画像显示
        updateUserProfile(profile);
        
    } catch (error) {
        console.error('加载用户画像失败:', error);
        // 如果用户不存在，创建新用户
        if (error.message.includes('404')) {
            elements.userStats.innerHTML = '<div class="stat-item">新用户，开始你的第一次对话吧！</div>';
        }
    }
}

// 加载历史对话列表
async function loadConversationHistory(userId) {
    try {
        const apiUrl = `${CONFIG.apiUrl}/users/${userId}/conversations`;
        const response = await fetch(apiUrl, {
            headers: getAuthHeaders()
        });
        
        if (!response.ok) {
            throw new Error(`获取历史对话失败: ${response.status}`);
        }
        
        const data = await response.json();
        state.conversations = data.conversations || [];
        
        // 渲染历史对话列表
        renderConversationHistory(state.conversations);
        
    } catch (error) {
        console.error('加载历史对话失败:', error);
        elements.historyList.innerHTML = '<div class="empty-state"><p>加载历史对话失败</p></div>';
    }
}

// 渲染历史对话列表
function renderConversationHistory(conversations) {
    if (!conversations || conversations.length === 0) {
        elements.historyList.innerHTML = '<div class="empty-state"><p>暂无历史对话</p></div>';
        return;
    }
    
    const html = conversations.map(conv => {
        const date = conv.updated_at || conv.created_at;
        const dateStr = date ? new Date(date).toLocaleString('zh-CN') : '未知时间';
        const stateClass = conv.state === 'completed' ? 'completed' : 'in-progress';
        const stateText = conv.state === 'completed' ? '已完成' : '进行中';
        
        return `
            <div class="history-item ${stateClass}" data-conversation-id="${conv.conversation_id}">
                <div class="history-item-header">
                    <span class="history-item-state">${stateText}</span>
                    <span class="history-item-date">${dateStr}</span>
                </div>
                <div class="history-item-content">
                    <div class="history-item-rounds">${conv.round_count} 轮对话</div>
                    <div class="history-item-question">${conv.last_question || '无问题'}</div>
                </div>
                <button class="btn btn-small" onclick="loadConversation('${conv.conversation_id}')">加载</button>
            </div>
        `;
    }).join('');
    
    elements.historyList.innerHTML = html;
}

// 切换历史对话列表显示
function toggleHistoryList() {
    state.historyExpanded = !state.historyExpanded;
    if (state.historyExpanded) {
        elements.historyList.style.display = 'block';
        elements.historyToggle.textContent = '▲';
    } else {
        elements.historyList.style.display = 'none';
        elements.historyToggle.textContent = '▼';
    }
}

// 加载指定对话（全局函数，供HTML调用）
window.loadConversation = async function(conversationId) {
    if (!state.userId) {
        alert('请先登录');
        return;
    }
    
    try {
        // 关闭当前WebSocket连接
        if (state.ws) {
            state.ws.close();
            state.ws = null;
        }
        
        // 获取对话信息
        const apiUrl = `${CONFIG.apiUrl}/conversations/${conversationId}`;
        const response = await fetch(apiUrl, {
            headers: getAuthHeaders()
        });
        
        if (!response.ok) {
            throw new Error(`获取对话失败: ${response.status}`);
        }
        
        const convInfo = await response.json();
        
        // 设置conversationId
        state.conversationId = conversationId;
        
        // 先获取对话的历史消息
        const messagesUrl = `${CONFIG.apiUrl}/conversations/${conversationId}/messages`;
        const messagesResponse = await fetch(messagesUrl, {
            headers: getAuthHeaders()
        });
        
        if (messagesResponse.ok) {
            const messagesData = await messagesResponse.json();
            // 清空当前对话列表
            elements.conversationList.innerHTML = '';
            
            // 渲染历史消息
            if (messagesData.messages && messagesData.messages.length > 0) {
                messagesData.messages.forEach(msg => {
                    const role = msg.role === 'assistant' ? 'assistant' : 'user';
                    // 使用消息的实际时间戳
                    const timestamp = msg.timestamp || msg.created_at || null;
                    addMessage(role, msg.content, false, timestamp);
                });
            } else {
                elements.conversationList.innerHTML = '<div class="empty-state"><p>暂无消息</p></div>';
            }
        }
        
        // 连接到WebSocket
        await connectWebSocket(conversationId);
        
        // 更新状态
        updateStatus('已加载对话', 'connected');
        
        // 刷新历史对话列表
        await loadConversationHistory(state.userId);
        
    } catch (error) {
        console.error('加载对话失败:', error);
        alert('加载对话失败: ' + error.message);
    }
};

// 开始对话
async function startConversation() {
    if (!state.userId) {
        alert('请先登录');
        return;
    }
    
    const userId = state.userId;
    
    try {
        // 先通过HTTP API创建对话
        const apiUrl = `${CONFIG.apiUrl}/conversations/start`;
        console.log('请求URL:', apiUrl);
        console.log('请求数据:', { user_id: userId });
        
        const response = await fetch(apiUrl, {
            method: 'POST',
            headers: getAuthHeaders(),
            body: JSON.stringify({ user_id: userId })
        });
        
        console.log('响应状态:', response.status, response.statusText);
        
        if (!response.ok) {
            // 尝试获取错误详情
            let errorMessage = `创建对话失败 (${response.status})`;
            try {
                const errorText = await response.text();
                if (errorText) {
                    try {
                        // 尝试解析为JSON
                        const errorData = JSON.parse(errorText);
                        errorMessage = errorData.detail || errorData.message || errorMessage;
                    } catch (e) {
                        // 如果不是JSON，直接使用文本
                        errorMessage += ': ' + errorText;
                    }
                }
            } catch (e) {
                // 如果读取失败，使用默认错误信息
                console.error('读取错误响应失败:', e);
            }
            throw new Error(errorMessage);
        }
        
        const data = await response.json();
        console.log('响应数据:', data);
        
        if (!data.conversation_id) {
            throw new Error('响应中缺少conversation_id');
        }
        
        state.conversationId = data.conversation_id;
        
        // 连接WebSocket
        await connectWebSocket();
        
        // 显示初始问题
        if (data.initial_question) {
            addMessage('assistant', data.initial_question);
        }
        
        // 更新UI
        elements.startBtn.disabled = true;
        elements.recordBtn.disabled = false;
        updateStatus('已连接', 'connected');
        
        // 刷新历史对话列表
        if (state.userId) {
            await loadConversationHistory(state.userId);
        }
        
    } catch (error) {
        console.error('开始对话失败:', error);
        const errorMsg = error.message || '未知错误';
        showError('开始对话失败: ' + errorMsg);
        // 重置UI状态
        elements.startBtn.disabled = false;
        elements.recordBtn.disabled = true;
    }
}

// 连接WebSocket
function connectWebSocket(conversationId = null) {
    const targetConversationId = conversationId || state.conversationId;
    if (!targetConversationId) {
        showError('请先开始对话');
        return Promise.reject(new Error('No conversation ID'));
    }
    
    return new Promise((resolve, reject) => {
        // 根据处理模式选择不同的WebSocket端点
        let wsEndpoint;
        if (state.processingMode === 'gpt4o-audio') {
            wsEndpoint = `/gpt4o-audio/${targetConversationId}/chat`;
            console.log('使用GPT-4o Audio模式');
        } else {
            wsEndpoint = `/streaming-voice/${targetConversationId}/chat`;
            console.log('使用标准模式');
        }
        
        const wsUrl = `${CONFIG.wsUrl}${wsEndpoint}`;
        state.ws = new WebSocket(wsUrl);
        state.conversationId = targetConversationId;
        
        state.ws.onopen = () => {
            console.log('WebSocket连接已建立');
            updateStatus('已连接', 'connected');
            elements.recordBtn.disabled = false;
            resolve();
        };
        
        state.ws.onerror = (error) => {
            console.error('WebSocket错误:', error);
            updateStatus('连接错误', 'disconnected');
            reject(error);
        };
    
        state.ws.onmessage = async (event) => {
            try {
                // 处理文本消息（JSON）
                if (typeof event.data === 'string') {
                    const message = JSON.parse(event.data);
                    await handleWebSocketMessage(message);
                } else {
                    // 处理二进制消息（音频数据）- 这种情况不应该发生，因为我们只发送文本
                    console.warn('收到意外的二进制消息');
                }
            } catch (error) {
                console.error('处理WebSocket消息失败:', error);
            }
        };
        
        state.ws.onclose = () => {
            console.log('WebSocket连接已关闭');
            updateStatus('已断开', 'disconnected');
            elements.recordBtn.disabled = true;
        };
    });
}

// 处理WebSocket消息
async function handleWebSocketMessage(message) {
    const { type, ...data } = message;
    
    switch (type) {
        case 'connected':
            const mode = data.mode || 'standard';
            console.log(`已连接到语音服务 (模式: ${mode})`);
            if (mode === 'gpt4o-audio') {
                showStatus('已连接 (GPT-4o Audio模式)', 'connected');
            }
            break;
            
        case 'recording_started':
            updateRecordingStatus('正在录音...');
            break;
            
        case 'transcription_partial':
            // 实时转录部分结果
            if (!performanceTimings.firstTranscription) {
                performanceTimings.firstTranscription = Date.now();
            }
            updateRealtimeTranscription(data.text);
            updatePerformanceMetrics();
            break;
            
        case 'transcription_final':
            // 最终转录结果
            performanceTimings.finalTranscription = Date.now();
            clearRealtimeTranscription();
            // 使用后端返回的时间戳，如果没有则使用当前时间
            addMessage('user', data.text, true, data.timestamp || null);
            updatePerformanceMetrics();
            break;
            
        case 'processing':
            updateRecordingStatus(data.message || '处理中...');
            break;
            
        case 'question':
            performanceTimings.questionReceived = Date.now();
            // 使用后端返回的时间戳，如果没有则使用当前时间
            addMessage('assistant', data.text, false, data.timestamp || null);
            console.log('收到问题文本:', data.text);
            console.log('等待TTS音频...');
            updatePerformanceMetrics();
            break;
            
        case 'audio_chunk':
            if (!performanceTimings.ttsStart) {
                performanceTimings.ttsStart = Date.now();
                console.log('收到第一个音频块，开始播放...');
            }
            await playAudioChunk(data.data);
            updatePerformanceMetrics();
            break;
            
        case 'audio_end':
            performanceTimings.ttsEnd = Date.now();
            console.log(`[流式TTS] 收到音频结束标记，共收到 ${audioState.totalReceived} 块`);
            updateRecordingStatus('语音播放中...');
            // 重置性能测试按钮
            if (elements.performanceTestBtn) {
                elements.performanceTestBtn.disabled = false;
                elements.performanceTestBtn.textContent = '🚀 开始性能测试';
            }
            // 标记不再接收新数据，但让当前队列播放完成
            state.audioQueuePlayer = false;
            // 如果队列中还有数据且没有在播放，继续播放
            if (audioState.queue.length > 0 && !audioState.isPlaying) {
                playNextChunk();
            }
            updatePerformanceMetrics();
            break;
            
        case 'assessment':
            performanceTimings.assessmentReceived = Date.now();
            console.log('收到评估数据:', data);
            if (data && data.data) {
                if (data.data.assessment) {
                    const isQuick = data.data.assessment.is_quick === true;
                    console.log(`开始更新评估显示... (${isQuick ? '快速评估' : '完整评估'})`);
                    updateAssessment(data.data, isQuick);
                    updatePerformanceMetrics();
                    // 显示更新提示
                    showStatus(isQuick ? '快速评估已更新（完整评估进行中...）' : '完整评估已更新', 'success');
                } else {
                    console.warn('评估数据格式不正确: assessment字段缺失', data.data);
                }
            } else {
                console.error('评估数据格式错误: data字段缺失', data);
            }
            break;
            
        case 'assessment_full':
            // 完整评估结果（异步评估完成后）
            console.log('收到完整评估数据:', data);
            if (data && data.data && data.data.assessment) {
                console.log('更新完整评估显示...');
                updateAssessment(data.data, false);
                showStatus('完整评估已更新', 'success');
            }
            break;
        
        // GPT-4o Audio 模式特有的消息类型
        case 'transcription':
            // GPT-4o Audio模式的转录结果
            performanceTimings.finalTranscription = Date.now();
            clearRealtimeTranscription();
            addMessage('user', data.text, true, data.timestamp || null);
            console.log('[GPT-4o Audio] 转录结果:', data.text);
            updatePerformanceMetrics();
            break;
            
        case 'evaluation':
            // GPT-4o Audio模式的评估结果
            performanceTimings.assessmentReceived = Date.now();
            console.log('[GPT-4o Audio] 评估数据:', data);
            if (data && data.data) {
                updateAssessment(data.data, false);
                if (data.data.assessment?.is_gpt4o_audio) {
                    showStatus('GPT-4o Audio评估完成', 'success');
                }
            }
            updatePerformanceMetrics();
            break;
            
        case 'response':
            // GPT-4o Audio模式的响应/问题（非流式）
            performanceTimings.questionReceived = Date.now();
            addMessage('assistant', data.text, false, data.timestamp || null);
            console.log('[GPT-4o Audio] 响应:', data.text);
            updatePerformanceMetrics();
            break;
        
        case 'response_chunk':
            // GPT-4o Audio流式响应片段
            if (!state.streamingMessageId) {
                // 创建新的流式消息
                state.streamingMessageId = createStreamingMessage();
                performanceTimings.firstChunkReceived = Date.now();
                console.log('[GPT-4o Audio Stream] 首字延迟:', Date.now() - performanceTimings.audioSent, 'ms');
            }
            // 追加文本到流式消息
            appendToStreamingMessage(data.content);
            break;
            
        case 'response_complete':
            // GPT-4o Audio流式响应完成
            performanceTimings.questionReceived = Date.now();
            if (state.streamingMessageId) {
                finalizeStreamingMessage(data.text, data.timestamp);
                state.streamingMessageId = null;
            } else {
                addMessage('assistant', data.text, false, data.timestamp || null);
            }
            console.log('[GPT-4o Audio Stream] 响应完成:', data.text?.substring(0, 50));
            updatePerformanceMetrics();
            break;
            
        case 'stats':
            // 性能统计
            console.log('[性能统计]', data.data);
            if (data.data) {
                const statsHtml = `
                    <div class="stats-info">
                        <span>处理模式: ${data.data.mode || 'standard'}</span>
                        ${data.data.gpt4o_time_ms ? `<span>GPT-4o: ${data.data.gpt4o_time_ms}ms</span>` : ''}
                        <span>总耗时: ${data.data.total_time_ms}ms</span>
                    </div>
                `;
                updateRecordingStatus(statsHtml);
            }
            break;
            
        case 'error':
            showError(data.message);
            break;
            
        default:
            console.log('未知消息类型:', type, data);
    }
}

// 切换录音状态
async function toggleRecording() {
    if (state.isRecording) {
        stopRecording();
    } else {
        await startRecording();
    }
}

// 开始录音
async function startRecording() {
    try {
        // 请求麦克风权限
        state.audioStream = await navigator.mediaDevices.getUserMedia({
            audio: {
                sampleRate: CONFIG.sampleRate,
                channelCount: CONFIG.channels,
                echoCancellation: true,
                noiseSuppression: true
            }
        });
        
        // 创建MediaRecorder
        const options = {
            mimeType: 'audio/webm;codecs=opus',
            audioBitsPerSecond: 128000
        };
        
        // 检查浏览器支持
        if (!MediaRecorder.isTypeSupported(options.mimeType)) {
            options.mimeType = 'audio/webm';
            if (!MediaRecorder.isTypeSupported(options.mimeType)) {
                options.mimeType = '';
            }
        }
        
        state.mediaRecorder = new MediaRecorder(state.audioStream, options);
        state.audioChunks = [];
        state.realtimeChunks = []; // 用于实时转录的音频块
        state.lastRealtimeSend = 0; // 上次发送实时转录的时间
        
        state.mediaRecorder.ondataavailable = async (event) => {
            if (event.data.size > 0) {
                state.audioChunks.push(event.data);
                state.realtimeChunks.push(event.data);
                
                // 实时转录：每300ms发送一次（降低延迟）
                const now = Date.now();
                if (now - state.lastRealtimeSend >= 300 && state.realtimeChunks.length >= 3) {
                    state.lastRealtimeSend = now;
                    const chunksToSend = [...state.realtimeChunks];
                    state.realtimeChunks = []; // 立即清空，避免重复发送
                    sendRealtimeTranscriptionAsync(chunksToSend); // 异步发送，不阻塞
                }
            }
        };
        
        state.mediaRecorder.onstop = async () => {
            // 发送剩余的实时转录
            if (state.realtimeChunks.length > 0) {
                await sendRealtimeTranscription();
            }
            // 发送完整音频
            await sendAudioToServer();
        };
        
        // 开始录音 - 每50ms收集一次数据（更细粒度）
        state.mediaRecorder.start(50);
        state.isRecording = true;
        
        // 记录性能数据
        performanceTimings.recordingStart = Date.now();
        
        // 更新UI
        elements.recordBtn.classList.add('recording');
        elements.recordBtn.querySelector('.record-text').textContent = '停止录音';
        updateRecordingStatus('正在录音...');
        updateStatus('recording', '录音中');
        clearRealtimeTranscription(); // 清除之前的转录
        
    } catch (error) {
        console.error('开始录音失败:', error);
        showError('无法访问麦克风: ' + error.message);
        state.isRecording = false;
    }
}

// 停止录音
function stopRecording() {
    if (state.mediaRecorder && state.isRecording) {
        state.mediaRecorder.stop();
        state.audioStream.getTracks().forEach(track => track.stop());
        state.isRecording = false;
        
        // 记录性能数据
        performanceTimings.recordingEnd = Date.now();
        
        // 更新UI
        elements.recordBtn.classList.remove('recording');
        elements.recordBtn.querySelector('.record-text').textContent = '开始录音';
        updateRecordingStatus('正在处理...');
        // 保持实时转录显示，直到最终结果返回
    }
}

// 发送实时转录音频块（同步版本，用于录音结束时）
async function sendRealtimeTranscription() {
    if (state.realtimeChunks.length === 0 || !state.ws || state.ws.readyState !== WebSocket.OPEN) {
        return;
    }
    await sendRealtimeTranscriptionAsync(state.realtimeChunks);
}

// 发送实时转录音频块（异步版本，不阻塞录音）
async function sendRealtimeTranscriptionAsync(chunks) {
    if (!chunks || chunks.length === 0 || !state.ws || state.ws.readyState !== WebSocket.OPEN) {
        return;
    }
    
    try {
        // 合并实时音频块
        const audioBlob = new Blob(chunks, { type: 'audio/webm' });
        const arrayBuffer = await audioBlob.arrayBuffer();
        
        // 降低最小音频大小要求（更快响应）
        if (arrayBuffer.byteLength < 1000) { // 小于1KB可能太短
            return;
        }
        
        // 发送实时转录请求
        if (state.ws && state.ws.readyState === WebSocket.OPEN) {
            const base64Data = arrayBufferToBase64(arrayBuffer);
            state.ws.send(JSON.stringify({
                type: 'realtime_transcribe',
                audio_data: base64Data
            }));
        }
    } catch (error) {
        console.error('发送实时转录失败:', error);
    }
}

// ArrayBuffer转Base64
function arrayBufferToBase64(buffer) {
    const bytes = new Uint8Array(buffer);
    let binary = '';
    for (let i = 0; i < bytes.byteLength; i++) {
        binary += String.fromCharCode(bytes[i]);
    }
    return btoa(binary);
}

// 发送音频到服务器
async function sendAudioToServer() {
    if (state.audioChunks.length === 0) {
        return;
    }
    
    try {
        // 合并音频块
        const audioBlob = new Blob(state.audioChunks, { type: 'audio/webm' });
        
        // 转换为ArrayBuffer
        const arrayBuffer = await audioBlob.arrayBuffer();
        
        // 根据处理模式选择不同的发送方式
        if (state.processingMode === 'gpt4o-audio') {
            // GPT-4o Audio模式：发送完整音频的base64编码
            await sendAudioForGPT4oAudio(arrayBuffer);
        } else {
            // 标准模式：分块发送二进制数据
            await sendAudioStandardMode(arrayBuffer);
        }
        
        // 清空音频块
        state.audioChunks = [];
        
        // 更新性能指标
        updatePerformanceMetrics();
        
    } catch (error) {
        console.error('发送音频失败:', error);
        showError('发送音频失败: ' + error.message);
    }
}

// 标准模式发送音频（分块二进制）
async function sendAudioStandardMode(arrayBuffer) {
    const chunkSize = 8192; // 8KB chunks
    const buffer = new Uint8Array(arrayBuffer);
    
    // 先发送开始标记
    if (state.ws && state.ws.readyState === WebSocket.OPEN) {
        state.ws.send(JSON.stringify({ type: 'start' }));
    }
    
    // 发送音频数据块（二进制）
    for (let i = 0; i < buffer.length; i += chunkSize) {
        const chunk = buffer.slice(i, i + chunkSize);
        if (state.ws && state.ws.readyState === WebSocket.OPEN) {
            state.ws.send(chunk);
        }
    }
    
    // 发送结束标记
    if (state.ws && state.ws.readyState === WebSocket.OPEN) {
        state.ws.send(JSON.stringify({ type: 'audio_end' }));
        performanceTimings.audioSent = Date.now();
    }
}

// GPT-4o Audio模式发送音频（base64编码）
async function sendAudioForGPT4oAudio(arrayBuffer) {
    console.log('[GPT-4o Audio] 发送音频，大小:', arrayBuffer.byteLength, 'bytes');
    
    // 先发送开始标记
    if (state.ws && state.ws.readyState === WebSocket.OPEN) {
        state.ws.send(JSON.stringify({ type: 'start' }));
    }
    
    // 将音频转换为base64并发送
    const base64Data = arrayBufferToBase64(arrayBuffer);
    
    if (state.ws && state.ws.readyState === WebSocket.OPEN) {
        state.ws.send(JSON.stringify({
            type: 'audio_data',
            data: base64Data
        }));
    }
    
    // 发送结束标记，触发处理
    if (state.ws && state.ws.readyState === WebSocket.OPEN) {
        state.ws.send(JSON.stringify({ type: 'audio_end' }));
        performanceTimings.audioSent = Date.now();
        console.log('[GPT-4o Audio] 音频已发送，等待处理...');
    }
}

// ========== 真正的流式音频播放 ==========
// 使用队列管理，实现边接收边播放

// 音频播放状态
const audioState = {
    queue: [],           // 音频块队列
    isPlaying: false,    // 是否正在播放
    currentAudio: null,  // 当前播放的Audio对象
    totalReceived: 0,    // 接收的总块数
    totalPlayed: 0,      // 播放的总块数
    firstChunkTime: 0,   // 第一个块接收时间
    playStartTime: 0     // 开始播放时间
};

// 接收音频块（立即加入队列并尝试播放）
async function playAudioChunk(base64Data) {
    try {
        // 解码base64
        const binaryString = atob(base64Data);
        const bytes = new Uint8Array(binaryString.length);
        for (let i = 0; i < binaryString.length; i++) {
            bytes[i] = binaryString.charCodeAt(i);
        }
        
        // 记录第一个块的接收时间
        if (audioState.totalReceived === 0) {
            audioState.firstChunkTime = Date.now();
            console.log(`[流式TTS] 收到第一个音频块，大小: ${bytes.length} bytes`);
        }
        
        audioState.totalReceived++;
        
        // 添加到队列
        audioState.queue.push(bytes);
        
        // 标记播放器活跃
        state.audioQueuePlayer = true;
        
        // 如果没有在播放，立即开始播放
        if (!audioState.isPlaying) {
            playNextChunk();
        }
        
    } catch (error) {
        console.error('处理音频块失败:', error);
    }
}

// 播放下一个音频块
async function playNextChunk() {
    // 如果队列为空且播放器已关闭，停止
    if (audioState.queue.length === 0) {
        if (!state.audioQueuePlayer) {
            audioState.isPlaying = false;
            console.log(`[流式TTS] 播放完成，共播放 ${audioState.totalPlayed} 块`);
            resetAudioState();
        } else {
            // 等待更多数据（短暂等待）
            audioState.isPlaying = false;
            setTimeout(() => {
                if (audioState.queue.length > 0 && !audioState.isPlaying) {
                    playNextChunk();
                }
            }, 50);
        }
        return;
    }
    
    audioState.isPlaying = true;
    
    // 记录播放开始时间
    if (audioState.playStartTime === 0) {
        audioState.playStartTime = Date.now();
        const latency = audioState.playStartTime - audioState.firstChunkTime;
        console.log(`[流式TTS] 开始播放，首块延迟: ${latency}ms`);
    }
    
    // 取出当前块播放
    const chunk = audioState.queue.shift();
    audioState.totalPlayed++;
    
    // 创建Blob并播放
    const blob = new Blob([chunk], { type: 'audio/mpeg' });
    const url = URL.createObjectURL(blob);
    
    const audio = new Audio(url);
    audio.volume = 1.0;
    audioState.currentAudio = audio;
    
    // 播放完成后立即播放下一个
    audio.onended = () => {
        URL.revokeObjectURL(url);
        audioState.currentAudio = null;
        // 立即播放下一个块（无缝衔接）
        playNextChunk();
    };
    
    audio.onerror = (e) => {
        console.error('音频播放错误:', e);
        URL.revokeObjectURL(url);
        audioState.currentAudio = null;
        // 继续播放下一个
        playNextChunk();
    };
    
    try {
        await audio.play();
    } catch (err) {
        console.error('播放失败:', err);
        // 尝试继续
        playNextChunk();
    }
}

// 重置音频状态
function resetAudioState() {
    audioState.queue = [];
    audioState.totalReceived = 0;
    audioState.totalPlayed = 0;
    audioState.firstChunkTime = 0;
    audioState.playStartTime = 0;
}

// 兼容旧代码的变量
let audioChunks = audioState.queue;

// 旧的播放队列函数（保持兼容性）
async function playAudioQueue() {
    // 这个函数现在由 playNextChunk 替代
    // 保留空实现以兼容可能的调用
}

// 添加消息到对话列表
function addMessage(role, content, isTranscription = false, timestamp = null) {
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message';
    
    // 使用提供的时间戳，如果没有则使用当前时间
    let messageTime;
    if (timestamp) {
        // 尝试解析时间戳（支持ISO格式和Unix时间戳）
        try {
            if (typeof timestamp === 'string' && timestamp.includes('T')) {
                // ISO格式时间戳
                messageTime = new Date(timestamp);
            } else if (typeof timestamp === 'number') {
                // Unix时间戳（毫秒）
                messageTime = new Date(timestamp);
            } else {
                messageTime = new Date(timestamp);
            }
            // 验证时间是否有效
            if (isNaN(messageTime.getTime())) {
                messageTime = new Date();
            }
        } catch (e) {
            console.warn('时间戳解析失败，使用当前时间:', timestamp, e);
            messageTime = new Date();
        }
    } else {
        messageTime = new Date();
    }
    
    // 格式化时间显示（包含毫秒以区分同一秒内的消息）
    const hours = String(messageTime.getHours()).padStart(2, '0');
    const minutes = String(messageTime.getMinutes()).padStart(2, '0');
    const seconds = String(messageTime.getSeconds()).padStart(2, '0');
    const milliseconds = String(messageTime.getMilliseconds()).padStart(3, '0');
    const timeStr = `${hours}:${minutes}:${seconds}.${milliseconds}`;
    
    messageDiv.innerHTML = `
        <div class="message-header">
            <span class="message-role ${role}">${role === 'assistant' ? '助手' : '用户'}</span>
            <span class="message-time">${timeStr}</span>
        </div>
        <div class="message-content ${isTranscription ? 'transcription' : ''}">
            ${escapeHtml(content)}
        </div>
    `;
    
    // 移除空状态
    const emptyState = elements.conversationList.querySelector('.empty-state');
    if (emptyState) {
        emptyState.remove();
    }
    
    elements.conversationList.appendChild(messageDiv);
    elements.conversationList.scrollTop = elements.conversationList.scrollHeight;
}

// ========== 流式消息处理 ==========

// 创建流式消息容器
function createStreamingMessage() {
    const messageId = 'streaming-' + Date.now();
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message streaming';
    messageDiv.id = messageId;
    
    const now = new Date();
    const hours = String(now.getHours()).padStart(2, '0');
    const minutes = String(now.getMinutes()).padStart(2, '0');
    const seconds = String(now.getSeconds()).padStart(2, '0');
    const timeStr = `${hours}:${minutes}:${seconds}`;
    
    messageDiv.innerHTML = `
        <div class="message-header">
            <span class="message-role assistant">助手</span>
            <span class="message-time">${timeStr}</span>
            <span class="streaming-indicator">⚡ 生成中...</span>
        </div>
        <div class="message-content streaming-content"></div>
    `;
    
    // 移除空状态
    const emptyState = elements.conversationList.querySelector('.empty-state');
    if (emptyState) {
        emptyState.remove();
    }
    
    elements.conversationList.appendChild(messageDiv);
    elements.conversationList.scrollTop = elements.conversationList.scrollHeight;
    
    return messageId;
}

// 追加文本到流式消息
function appendToStreamingMessage(content) {
    if (!state.streamingMessageId) return;
    
    const messageDiv = document.getElementById(state.streamingMessageId);
    if (messageDiv) {
        const contentDiv = messageDiv.querySelector('.streaming-content');
        if (contentDiv) {
            // 追加文本（保留HTML转义）
            contentDiv.textContent += content;
            elements.conversationList.scrollTop = elements.conversationList.scrollHeight;
        }
    }
}

// 完成流式消息
function finalizeStreamingMessage(fullText, timestamp) {
    if (!state.streamingMessageId) return;
    
    const messageDiv = document.getElementById(state.streamingMessageId);
    if (messageDiv) {
        // 移除流式状态
        messageDiv.classList.remove('streaming');
        
        // 更新时间戳
        if (timestamp) {
            const timeSpan = messageDiv.querySelector('.message-time');
            if (timeSpan) {
                const messageTime = new Date(timestamp);
                const hours = String(messageTime.getHours()).padStart(2, '0');
                const minutes = String(messageTime.getMinutes()).padStart(2, '0');
                const seconds = String(messageTime.getSeconds()).padStart(2, '0');
                const milliseconds = String(messageTime.getMilliseconds()).padStart(3, '0');
                timeSpan.textContent = `${hours}:${minutes}:${seconds}.${milliseconds}`;
            }
        }
        
        // 移除流式指示器
        const indicator = messageDiv.querySelector('.streaming-indicator');
        if (indicator) {
            indicator.remove();
        }
        
        // 更新内容（使用完整文本）
        const contentDiv = messageDiv.querySelector('.streaming-content');
        if (contentDiv) {
            contentDiv.classList.remove('streaming-content');
            contentDiv.textContent = fullText || contentDiv.textContent;
        }
    }
}

// 更新评估结果
function updateAssessment(data, isQuick = false) {
    console.log('updateAssessment 被调用，数据:', data, 'isQuick:', isQuick);
    const { assessment, user_profile } = data;
    
    if (!assessment) {
        console.warn('updateAssessment: assessment 为空', data);
        return;
    }
    
    const assessmentType = isQuick ? '（快速评估）' : '（完整评估）';
    console.log(`更新评估显示${assessmentType}，分数:`, assessment.overall_score, '等级:', assessment.cefr_level);
    
    // 更新评估显示
    const scoreClass = assessment.overall_score >= 75 ? 'high' : 
                       assessment.overall_score >= 50 ? 'medium' : 'low';
    
    elements.assessmentContent.innerHTML = `
        <div class="profile-item">
            <span class="profile-label">综合分数:</span>
            <span class="score-badge ${scoreClass}">${assessment.overall_score.toFixed(1)}/100</span>
            ${isQuick ? '<span style="font-size: 10px; color: #6c757d; margin-left: 5px;">（快速）</span>' : ''}
        </div>
        <div class="profile-item">
            <span class="profile-label">CEFR等级:</span>
            <span class="cefr-badge">${assessment.cefr_level}</span>
            ${isQuick ? '<span style="font-size: 10px; color: #6c757d; margin-left: 5px;">（快速）</span>' : ''}
        </div>
        ${assessment.confidence !== undefined ? `
            <div class="profile-item">
                <span class="profile-label">置信度:</span>
                <span class="profile-value">${(assessment.confidence * 100).toFixed(0)}%</span>
            </div>
        ` : ''}
        ${assessment.strengths && assessment.strengths.length > 0 ? `
            <div class="profile-item">
                <span class="profile-label">强项:</span>
                <ul class="strengths-list">
                    ${assessment.strengths.map(s => `<li>${escapeHtml(s)}</li>`).join('')}
                </ul>
            </div>
        ` : ''}
        ${assessment.weaknesses && assessment.weaknesses.length > 0 ? `
            <div class="profile-item">
                <span class="profile-label">弱项:</span>
                <ul class="weaknesses-list">
                    ${assessment.weaknesses.map(w => `<li>${escapeHtml(w)}</li>`).join('')}
                </ul>
            </div>
        ` : ''}
    `;
    
    // 更新用户画像
    if (user_profile && Object.keys(user_profile).length > 0) {
        console.log('更新用户画像:', user_profile);
        elements.profileContent.innerHTML = `
            <div class="profile-item">
                <span class="profile-label">用户ID:</span>
                <span class="profile-value">${escapeHtml(user_profile.user_id || 'N/A')}</span>
            </div>
            <div class="profile-item">
                <span class="profile-label">综合分数:</span>
                <span class="score-badge ${scoreClass}">${user_profile.overall_score?.toFixed(1) || 'N/A'}/100</span>
            </div>
            <div class="profile-item">
                <span class="profile-label">CEFR等级:</span>
                <span class="cefr-badge">${user_profile.cefr_level || 'N/A'}</span>
            </div>
            <div class="profile-item">
                <span class="profile-label">对话轮数:</span>
                <span class="profile-value">${user_profile.conversation_count || 0}</span>
            </div>
        `;
    }
}

// 更新状态
function updateStatus(status, text) {
    elements.statusIndicator.className = `status-indicator ${status}`;
    elements.statusText.textContent = text;
}

// 更新录音状态
function updateRecordingStatus(text) {
    elements.recordingStatus.textContent = text;
    if (text.includes('录音')) {
        elements.recordingStatus.classList.add('active');
    } else {
        elements.recordingStatus.classList.remove('active');
    }
}

// 更新实时转录
// 实时转录状态
const transcriptionState = {
    currentText: '',
    isAnimating: false,
    animationQueue: []
};

// 更新实时转录（逐字显示效果）
function updateRealtimeTranscription(text) {
    if (elements.realtimeTranscription && elements.realtimeTranscriptionText) {
        elements.realtimeTranscription.style.display = 'block';
        
        // 如果新文本比当前文本长，逐字添加
        if (text.length > transcriptionState.currentText.length) {
            const newChars = text.slice(transcriptionState.currentText.length);
            transcriptionState.currentText = text;
            
            // 逐字显示新字符
            animateNewChars(newChars);
        } else {
            // 如果是新的转录结果（更短或完全不同），直接替换
            transcriptionState.currentText = text;
            elements.realtimeTranscriptionText.textContent = text;
        }
    }
}

// 逐字动画显示
function animateNewChars(chars) {
    // 将字符加入队列
    for (const char of chars) {
        transcriptionState.animationQueue.push(char);
    }
    
    // 如果没有在动画中，开始动画
    if (!transcriptionState.isAnimating) {
        processAnimationQueue();
    }
}

// 处理动画队列
function processAnimationQueue() {
    if (transcriptionState.animationQueue.length === 0) {
        transcriptionState.isAnimating = false;
        return;
    }
    
    transcriptionState.isAnimating = true;
    
    // 每次处理多个字符（加快显示速度）
    const charsToShow = transcriptionState.animationQueue.splice(0, 3);
    elements.realtimeTranscriptionText.textContent += charsToShow.join('');
    
    // 使用requestAnimationFrame实现平滑动画
    requestAnimationFrame(() => {
        setTimeout(processAnimationQueue, 20); // 20ms间隔
    });
}

// 清除实时转录
function clearRealtimeTranscription() {
    if (elements.realtimeTranscription) {
        elements.realtimeTranscription.style.display = 'none';
        if (elements.realtimeTranscriptionText) {
            elements.realtimeTranscriptionText.textContent = '';
        }
    }
    // 重置转录状态
    transcriptionState.currentText = '';
    transcriptionState.isAnimating = false;
    transcriptionState.animationQueue = [];
}

// 清空对话
function clearConversation() {
    if (confirm('确定要清空对话历史吗？')) {
        elements.conversationList.innerHTML = `
            <div class="empty-state">
                <p>对话将在这里显示</p>
            </div>
        `;
    }
}

// 显示错误
function showError(message) {
    console.error('错误:', message);
    // 使用更友好的错误提示
    const errorDiv = document.createElement('div');
    errorDiv.style.cssText = 'position: fixed; top: 20px; right: 20px; background: #dc3545; color: white; padding: 15px 20px; border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.3); z-index: 10000; max-width: 400px;';
    errorDiv.textContent = message;
    document.body.appendChild(errorDiv);
    
    // 3秒后自动移除
    setTimeout(() => {
        errorDiv.remove();
    }, 5000);
    
    updateStatus('disconnected', '错误');
}

// HTML转义
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// 性能测试
let performanceTimings = {
    recordingStart: null,
    recordingEnd: null,
    audioSent: null,
    firstTranscription: null,
    finalTranscription: null,
    assessmentReceived: null,
    questionReceived: null,
    ttsStart: null,
    ttsEnd: null
};

function startPerformanceTest() {
    if (!state.conversationId) {
        alert('请先开始对话');
        return;
    }
    
    // 重置性能数据
    performanceTimings = {
        recordingStart: null,
        recordingEnd: null,
        audioSent: null,
        firstTranscription: null,
        finalTranscription: null,
        assessmentReceived: null,
        questionReceived: null,
        ttsStart: null,
        ttsEnd: null
    };
    
    // 显示性能测试区域
    elements.performanceContent.style.display = 'block';
    elements.performanceMetrics.innerHTML = '<p style="color: #6c757d;">准备开始测试，请点击"开始录音"按钮...</p>';
    
    // 更新按钮状态
    elements.performanceTestBtn.disabled = true;
    elements.performanceTestBtn.textContent = '⏱️ 测试进行中...';
    
    // 监听性能事件
    setupPerformanceMonitoring();
}

function setupPerformanceMonitoring() {
    // 这个函数会在录音和处理过程中被调用
    // 性能数据会在各个事件处理函数中更新
}

function updatePerformanceMetrics() {
    if (!performanceTimings.recordingStart) {
        return; // 测试还未开始
    }
    
    const metrics = [];
    let totalTime = 0;
    
    // 录音时间
    if (performanceTimings.recordingStart && performanceTimings.recordingEnd) {
        const recordingTime = (performanceTimings.recordingEnd - performanceTimings.recordingStart) / 1000;
        metrics.push({
            label: '录音时间',
            value: recordingTime.toFixed(2) + 's',
            class: recordingTime < 5 ? 'fast' : (recordingTime < 10 ? 'medium' : 'slow')
        });
    }
    
    // 音频发送时间
    if (performanceTimings.recordingEnd && performanceTimings.audioSent) {
        const sendTime = (performanceTimings.audioSent - performanceTimings.recordingEnd) / 1000;
        metrics.push({
            label: '音频发送',
            value: sendTime.toFixed(2) + 's',
            class: sendTime < 0.5 ? 'fast' : (sendTime < 1 ? 'medium' : 'slow')
        });
    }
    
    // 首次转录时间
    if (performanceTimings.audioSent && performanceTimings.firstTranscription) {
        const transcriptionTime = (performanceTimings.firstTranscription - performanceTimings.audioSent) / 1000;
        metrics.push({
            label: '首次转录',
            value: transcriptionTime.toFixed(2) + 's',
            class: transcriptionTime < 1 ? 'fast' : (transcriptionTime < 3 ? 'medium' : 'slow')
        });
    }
    
    // 最终转录时间
    if (performanceTimings.audioSent && performanceTimings.finalTranscription) {
        const finalTranscriptionTime = (performanceTimings.finalTranscription - performanceTimings.audioSent) / 1000;
        metrics.push({
            label: '最终转录',
            value: finalTranscriptionTime.toFixed(2) + 's',
            class: finalTranscriptionTime < 1 ? 'fast' : (finalTranscriptionTime < 3 ? 'medium' : 'slow')
        });
        totalTime = finalTranscriptionTime;
    }
    
    // 评估处理时间
    if (performanceTimings.finalTranscription && performanceTimings.assessmentReceived) {
        const assessmentTime = (performanceTimings.assessmentReceived - performanceTimings.finalTranscription) / 1000;
        metrics.push({
            label: '评估处理',
            value: assessmentTime.toFixed(2) + 's',
            class: assessmentTime < 1 ? 'fast' : (assessmentTime < 2 ? 'medium' : 'slow')
        });
        totalTime = (performanceTimings.assessmentReceived - performanceTimings.audioSent) / 1000;
    }
    
    // 问题生成时间
    if (performanceTimings.assessmentReceived && performanceTimings.questionReceived) {
        const questionTime = (performanceTimings.questionReceived - performanceTimings.assessmentReceived) / 1000;
        metrics.push({
            label: '问题生成',
            value: questionTime.toFixed(2) + 's',
            class: questionTime < 1 ? 'fast' : (questionTime < 2 ? 'medium' : 'slow')
        });
        totalTime = (performanceTimings.questionReceived - performanceTimings.audioSent) / 1000;
    }
    
    // TTS时间
    if (performanceTimings.questionReceived && performanceTimings.ttsStart && performanceTimings.ttsEnd) {
        const ttsTime = (performanceTimings.ttsEnd - performanceTimings.ttsStart) / 1000;
        metrics.push({
            label: 'TTS生成',
            value: ttsTime.toFixed(2) + 's',
            class: ttsTime < 1 ? 'fast' : (ttsTime < 3 ? 'medium' : 'slow')
        });
        totalTime = (performanceTimings.ttsEnd - performanceTimings.audioSent) / 1000;
    }
    
    // 总时间
    if (performanceTimings.recordingStart && performanceTimings.ttsEnd) {
        const totalProcessTime = (performanceTimings.ttsEnd - performanceTimings.recordingStart) / 1000;
        metrics.push({
            label: '总耗时',
            value: totalProcessTime.toFixed(2) + 's',
            class: totalProcessTime < 5 ? 'fast' : (totalProcessTime < 10 ? 'medium' : 'slow')
        });
    }
    
    // 渲染指标
    if (metrics.length > 0) {
        let html = '<div class="performance-metrics">';
        metrics.forEach(metric => {
            html += `
                <div class="performance-metric">
                    <span class="metric-label">${metric.label}:</span>
                    <span class="metric-value ${metric.class}">${metric.value}</span>
                </div>
            `;
        });
        html += '</div>';
        
        // 添加总结
        if (totalTime > 0) {
            let summary = '';
            if (totalTime < 5) {
                summary = '✅ 性能优秀！响应速度很快。';
            } else if (totalTime < 10) {
                summary = '⚠️ 性能良好，但可以进一步优化。';
            } else {
                summary = '❌ 性能较慢，建议检查网络连接或服务配置。';
            }
            
            html += `
                <div class="performance-summary">
                    <h4>性能评估</h4>
                    <p>${summary}</p>
                    <p>总处理时间: ${totalTime.toFixed(2)}秒</p>
                </div>
            `;
        }
        
        elements.performanceMetrics.innerHTML = html;
    }
}

