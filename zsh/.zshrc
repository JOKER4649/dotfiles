# If you come from bash you might have to change your $PATH.
# export PATH=$HOME/bin:$HOME/.local/bin:/usr/local/bin:$PATH

# Path to your Oh My Zsh installation.
export ZSH="$HOME/.oh-my-zsh"

# Set name of the theme to load --- if set to "random", it will
# load a random theme each time Oh My Zsh is loaded, in which case,
# to know which specific one was loaded, run: echo $RANDOM_THEME
# See https://github.com/ohmyzsh/ohmyzsh/wiki/Themes
ZSH_THEME="robbyrussell"

# Set list of themes to pick from when loading at random
# Setting this variable when ZSH_THEME=random will cause zsh to load
# a theme from this variable instead of looking in $ZSH/themes/
# If set to an empty array, this variable will have no effect.
# ZSH_THEME_RANDOM_CANDIDATES=( "robbyrussell" "agnoster" )

# Uncomment the following line to use case-sensitive completion.
# CASE_SENSITIVE="true"

# Uncomment the following line to use hyphen-insensitive completion.
# Case-sensitive completion must be off. _ and - will be interchangeable.
# HYPHEN_INSENSITIVE="true"

# Uncomment one of the following lines to change the auto-update behavior
# zstyle ':omz:update' mode disabled  # disable automatic updates
zstyle ':omz:update' mode auto      # update automatically without asking
# zstyle ':omz:update' mode reminder  # just remind me to update when it's time

# Uncomment the following line to change how often to auto-update (in days).
# zstyle ':omz:update' frequency 13

# Uncomment the following line if pasting URLs and other text is messed up.
# DISABLE_MAGIC_FUNCTIONS="true"

# Uncomment the following line to disable colors in ls.
# DISABLE_LS_COLORS="true"

# Uncomment the following line to disable auto-setting terminal title.
# DISABLE_AUTO_TITLE="true"

# Uncomment the following line to enable command auto-correction.
#ENABLE_CORRECTION="true"

# Uncomment the following line to display red dots whilst waiting for completion.
# You can also set it to another string to have that shown instead of the default red dots.
# e.g. COMPLETION_WAITING_DOTS="%F{yellow}waiting...%f"
# Caution: this setting can cause issues with multiline prompts in zsh < 5.7.1 (see #5765)
# COMPLETION_WAITING_DOTS="true"

# Uncomment the following line if you want to disable marking untracked files
# under VCS as dirty. This makes repository status check for large repositories
# much, much faster.
DISABLE_UNTRACKED_FILES_DIRTY="true"

# Uncomment the following line if you want to change the command execution time
# stamp shown in the history command output.
# You can set one of the optional three formats:
# "mm/dd/yyyy"|"dd.mm.yyyy"|"yyyy-mm-dd"
# or set a custom format using the strftime function format specifications,
# see 'man strftime' for details.
# HIST_STAMPS="mm/dd/yyyy"

# Would you like to use another custom folder than $ZSH/custom?
# ZSH_CUSTOM=/path/to/new-custom-folder

# command 歷史長度
HISTSIZE=100000
SAVEHIST=100000

# Which plugins would you like to load?
# Standard plugins can be found in $ZSH/plugins/
# Custom plugins may be added to $ZSH_CUSTOM/plugins/
# Example format: plugins=(rails git textmate ruby lighthouse)
# Add wisely, as too many plugins slow down shell startup.
plugins=(
  git
  gitfast
  sudo
  history
	zsh-autosuggestions zsh-syntax-highlighting fast-syntax-highlighting 
)

source $ZSH/oh-my-zsh.sh

# User configuration

# export MANPATH="/usr/local/man:$MANPATH"

# You may need to manually set your language environment
# export LANG=en_US.UTF-8

# Preferred editor for local and remote sessions
# if [[ -n $SSH_CONNECTION ]]; then
#   export EDITOR='vim'
# else
#   export EDITOR='nvim'
# fi

# Compilation flags
# export ARCHFLAGS="-arch $(uname -m)"

# Set personal aliases, overriding those provided by Oh My Zsh libs,
# plugins, and themes. Aliases can be placed here, though Oh My Zsh
# users are encouraged to define aliases within a top-level file in
# the $ZSH_CUSTOM folder, with .zsh extension. Examples:
# - $ZSH_CUSTOM/aliases.zsh
# - $ZSH_CUSTOM/macos.zsh
# For a full list of active aliases, run `alias`.
#
# Example aliases
# alias zshconfig="mate ~/.zshrc"
# alias ohmyzsh="mate ~/.oh-my-zsh"
alias mi="mise install"
alias mr="mise run"

# SSH TERM 兼容性由 ssh/config 的 SetEnv 统一处理，避免每台主机安装 xterm-kitty terminfo。
# 需要 Kitty shell integration / keyboard protocol 时手动 opt-in。
kssh() {
  if [[ -n "$KITTY_PID" ]] && command -v kitty >/dev/null 2>&1; then
    command kitty +kitten ssh "$@"
  else
    command ssh "$@"
  fi
}

if (( $+functions[compdef] )); then
  compdef _ssh kssh
  (( $+functions[_gcloud] )) && compdef _gcloud gcloud
fi

eval "$(~/.local/bin/mise activate zsh)"

# 關閉 github cli 的翻頁
export GH_PAGER=cat

# 讓 bat/less 在 kitty、zellij、tmux 的 alternate screen 中也能直接吃滑鼠滾輪。
export LESS="--RAW-CONTROL-CHARS --quit-if-one-screen --mouse --wheel-lines=3"
export BAT_PAGER="less --RAW-CONTROL-CHARS --quit-if-one-screen --mouse --wheel-lines=3"

# portless: 使用 unprivileged port，避免 sudo（由 systemd user service 管理 proxy）
export PORTLESS_PORT=1355

if [[ -z "$OPENCODE" ]]; then
  eval "$(starship init zsh)"
fi

export EDITOR="code --wait"

# 自訂 CLI 命令
export PATH="$HOME/myconfig/commands:$PATH"

# Added by LM Studio CLI tool (lms)
export PATH="$PATH:/home/joker/.lmstudio/bin"
export OPENCODE_EXPERIMENTAL_DISABLE_COPY_ON_SELECT=true

# opencode
export OPENCODE_ENABLE_EXA=1

if command -v wt >/dev/null 2>&1; then eval "$(command wt config shell init zsh)"; fi

# opencode
export PATH=/home/joker/.opencode/bin:$PATH

# opencode: 個人設定 overlay（僅疊加於互動式呼叫）
# 用 wrapper function 而非 export，OPENCODE_CONFIG_DIR 只注入 opencode child，
# 不進 shell 環境，因此不會被 multica daemon（os.Environ() 繼承）等子行程帶走。
opencode() {
  OPENCODE_CONFIG_DIR="$HOME/myconfig/opencode-local" command opencode "$@"
}

# bun completions
[ -s "/home/joker/.bun/_bun" ] && source "/home/joker/.bun/_bun"
