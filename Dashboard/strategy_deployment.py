import streamlit as st
import multiprocessing
import time
import schedule
import uuid
import inspect
import datetime
from datetime import datetime as dt, date
import pandas as pd
import os
import json
import signal
from dotenv import load_dotenv
from strategy.strategy_registry import STRATEGY_REGISTRY
from finstore.finstore import Finstore
import json

# ---------------------------
# Live Deployment Fragment
# ---------------------------
@st.fragment(run_every=2000)  # Update every 2 seconds
def live_deployments(manager):
    """Fragment for real-time deployment monitoring"""
    # Use empty containers for dynamic updates
    status_container = st.container()
    controls_container = st.container()
    log_container = st.container()
    
    with status_container:
        st.subheader("Active Deployments")
        if not manager.deployments:
            st.info("No active deployments")
            return

        # Deployment Status Cards
        for dep_id, dep in list(manager.deployments.items()):
            cols = st.columns([1, 2, 1, 1])
            with cols[0]:
                st.markdown(f"**{dep_id}**")
                status = dep.get("status", "unknown")
                color = {"running": "🟢", "stopped": "🔴", "error": "🟠"}.get(status, "⚪")
                st.markdown(f"{color} **{status.title()}**")
            
            with cols[1]:
                st.caption(f"Strategy: {dep['config'].get('strategy_name', 'Unknown')}")
                st.caption(f"Market: {dep['config']['market_params']['market_name']}")

    with controls_container:
        # Interactive Controls
        for dep_id, dep in list(manager.deployments.items()):
            cols = st.columns([3, 1, 1])
            with cols[1]:
                if st.button("📋 Logs", key=f"logs_{dep_id}"):
                    st.session_state[f"show_logs_{dep_id}"] = not st.session_state.get(f"show_logs_{dep_id}", False)
            with cols[2]:
                if st.button("⏹ Stop", key=f"stop_{dep_id}"):
                    with st.spinner(f"Stopping {dep_id}..."):
                        manager.stop_deployment(dep_id)
                        st.rerun()

    with log_container:
        # Dynamic Log Display
        for dep_id in manager.deployments:
            if st.session_state.get(f"show_logs_{dep_id}"):
                with st.expander(f"Logs for {dep_id}", expanded=True):
                    log_content = read_log(dep_id)
                    if log_content:
                        st.download_button(
                            label="Download Full Log",
                            data=log_content,
                            file_name=f"{dep_id}_logs.txt",
                            key=f"dl_{dep_id}"
                        )
                        st.code("\n".join(log_content.split("\n")[-50:]))
                    else:
                        st.warning("No logs available")

    # Clear button outside containers
    if st.button("🧹 Clear Stopped Deployments"):
        with st.spinner("Cleaning up..."):
            manager._cleanup_zombies()
            st.rerun()

# ---------------------------
# Setup persistent storage paths
# ---------------------------
DEPLOYMENTS_FILE = "database/deployment/active_deployments.json"
LOG_DIR = "database/deployment/logs"
os.makedirs(LOG_DIR, exist_ok=True)

@st.cache_resource
def get_finstore(market_name, timeframe, pair=''):
    return Finstore(market_name=market_name, timeframe=timeframe, pair=pair)

# ---------------------------
# Enhanced Strategy Modules
# ---------------------------

if 'preloaded_params' not in st.session_state:
    st.session_state['preloaded_params'] = {}

def dynamic_strategy_loader():
    """Dynamically load strategies with parameter inspection"""
    strategies = {}

    for strategy_name, strategy_details in STRATEGY_REGISTRY.items():
        strategies[strategy_name] = {
            "func" : strategy_details['class'],
            "params" : get_strategy_params(strategy_details['class'])
        }
    return strategies

# ---------------------------
# Enhanced Parameter Handling
# ---------------------------
def get_strategy_params(cls):
    """Improved parameter extraction with type handling"""
    sig = inspect.signature(cls.__init__)
    params = {}
    for name, param in list(sig.parameters.items())[1:]:  # Skip ohlcv_data and symbol_list
        param_info = {
            "type": param.annotation,
            "default": param.default if param.default != inspect.Parameter.empty else None
        }
        
        # Set reasonable defaults for common parameter types
        if param_info["type"] == int:
            param_info["default"] = param_info["default"] or 20
            param_info["min"] = 1
            param_info["step"] = 1
        elif param_info["type"] == float:
            param_info["default"] = param_info["default"] or 0.0
            param_info["step"] = 0.001
        elif param_info["type"] == bool:
            param_info["default"] = param_info["default"] or False
            
        params[name] = param_info
    return params

# ---------------------------
# Enhanced Asset Selection
# ---------------------------
def asset_selection_widget(market_name, timeframe, default_symbols=None, default_pair_type=None):
    """Dynamic asset selection based on market type"""
    st.subheader("Asset Universe Selection")
    
    if market_name == "crypto_binance":
        pair_type = st.radio("Pair Type:", 
                             ["USDT", "BTC"], 
                             horizontal=True,
                             index=1 if default_pair_type == "BTC" else 0)
        symbols = get_finstore("crypto_binance", timeframe, pair=pair_type).read.get_symbol_list()
    elif market_name == "indian_equity":
        symbols = get_finstore("indian_equity", timeframe, pair="").read.get_symbol_list()
    else:
        symbols = []

    selected = st.multiselect(
        "Select assets:", 
        options=symbols,
        default=default_symbols if default_symbols != [] else symbols[:5]
    )
    return pair_type, selected

# ---------------------------
# Enhanced Scheduler Configuration
# ---------------------------
def scheduler_config_widget():
    """Improved scheduler input with timezone support"""
    st.subheader("Scheduler Configuration")
    col1, col2 = st.columns([1, 2])
    
    with col1:
        scheduler_type = st.selectbox(
            "Schedule Type", 
            options=["Fixed Interval", "Specific Time"]
        )
    
    with col2:
        if scheduler_type == "Fixed Interval":
            interval = st.number_input(
                "Interval (minutes)", 
                min_value=1, 
                value=60,
                help="How often to run the strategy"
            )
            return {"type": "fixed_interval", "value": interval}
        else:
            tz = st.selectbox(
                "Timezone",
                options=["UTC", "Asia/Kolkata", "America/New_York"],
                index=0
            )
            exec_time = st.time_input(
                "Execution Time", 
                value=datetime.time(9, 0),
                help="Local time for daily execution"
            )
            return {"type": "specific_time", "value": exec_time, "tz": tz}

# ---------------------------
# Enhanced OMS Configuration
# ---------------------------
def oms_config_widget(oms_type):
    """Modular OMS configuration with validation"""
    config = {}
    
    if oms_type == "Telegram":
        col1, col2 = st.columns(2)
        with col1:
            config['token'] = st.text_input(
                "Bot Token", 
                help="Get from @BotFather",
                type="password"
            )
        with col2:
            config['chat_id'] = st.text_input(
                "Chat ID",
                help="Use @getidsbot to find"
            )
            
    elif oms_type == "Zerodha":
        config['userid'] = st.text_input("User ID")
        config['password'] = st.text_input("Password", type="password")
        config['totp'] = st.text_input("TOTP Secret", type="password")
        
    elif oms_type == "Binance":
        config['api_key'] = st.text_input("API Key", type="password")
        config['api_secret'] = st.text_input("API Secret", type="password")
        
    return config


def serialize_deployment_config(config):
    serializable = config.copy()
    # Remove non-serializable entries
    if "oms_instance" in serializable:
        del serializable["oms_instance"]
    if "strategy_object" in serializable:
        del serializable["strategy_object"]
    return serializable

def load_active_deployments():
    if os.path.exists(DEPLOYMENTS_FILE):
        with open(DEPLOYMENTS_FILE, "r") as f:
            try:
                return json.load(f)
            except Exception:
                return {}
    return {}

def save_active_deployments(deployments):
    with open(DEPLOYMENTS_FILE, "w") as f:
        json.dump(deployments, f, indent=4)

def append_log(deployment_id, msg):
    timestamp = dt.now().strftime('%Y-%m-%d %H:%M:%S')
    log_line = f"[{timestamp}] {msg}\n"
    log_file = os.path.join(LOG_DIR, f"deployment_{deployment_id}.log")
    with open(log_file, "a") as f:
        f.write(log_line)
    print(log_line, end="")  # Also print to console

def read_log(deployment_id):
    log_file = os.path.join(LOG_DIR, f"deployment_{deployment_id}.log")
    if os.path.exists(log_file):
        with open(log_file, "r") as f:
            return f.read()
    return "No logs available."

# ---------------------------
# Deployment runner function for the process
# ---------------------------
def deployment_runner_process(deployment_id, config):
    """Run deployment using the Deployer class"""
    try:
        from deployment_engine.deployer import Deployer
        append_log(deployment_id, f"🚀 Starting deployment with Deployer class")
        
        # Convert OMS config to Deployer format
        oms_mapping = {
            "Telegram": ("Telegram", {'group_id': config['oms']['config'].get('chat_id')}),
            "Zerodha": ("indian_equity", {'broker_config': config['oms']['config']}),
            "Binance": ("crypto_binance", config['oms']['config'])
        }
        oms_name, oms_params = oms_mapping.get(config['oms_type'], (None, None))
        # Create Deployer instance
        if config['backtest_uuid']:
            try:
                from deployment_engine.deployer import Deployer
                deployer = Deployer.from_backtest_uuid(
                    backtest_uuid=config['backtest_uuid'],
                    oms_name=oms_name,
                    scheduler_type=config['scheduler_type'],
                    scheduler_interval=str(config['scheduler_interval']),
                    start_date = pd.Timestamp(config['deployer_params'].get('start_date')) if config['deployer_params'].get('start_date') else None,
                    end_date=pd.Timestamp.now() + pd.Timedelta(days=2),
                    init_cash=int(config['deployer_params'].get('init_cash', 100000)),
                    fees=0,
                    slippage=0,
                    size=int(config['deployer_params'].get('size', 1)),
                    cash_sharing=bool(config['deployer_params'].get('cash_sharing', False)),
                    allow_partial=bool(config['deployer_params'].get('allow_partial', False)),
                    oms_params=oms_params,
                    progress_callback=lambda p, s: append_log(deployment_id, f"PROGRESS: {p}% - {s}")
                )
            except Exception as e:
                st.error(f"Failed to load backtest: {str(e)}")
        else:
            # TODO : Remove fees , slippage , etc and make size , cash sharing , start date, end date etc parameters more configurable.
            deployer = Deployer(
                market_name=config['market_params']['market_name'],
                symbol_list=config['asset_universe'],
                timeframe=config['market_params']['timeframe'],
                scheduler_type=config['scheduler_type'],
                scheduler_interval=str(config['scheduler_interval']),
                strategy_object=config['strategy_object'],
                strategy_type=config['strategy_name'],
                start_date=config['deployer_params'].get('start_date'),
                end_date=pd.Timestamp.now() + pd.Timedelta(days=2),
                init_cash=int(config['deployer_params'].get('init_cash')),
                fees=0,
                slippage=0,
                size=int(config['deployer_params'].get('size')),
                cash_sharing=bool(config['deployer_params'].get('cash_sharing')),
                allow_partial=bool(config['deployer_params'].get('allow_partial')),
                oms_name=oms_name,
                pair=config['market_params'].get('pair'),
                oms_params=oms_params,
                progress_callback=lambda p, s: append_log(deployment_id, f"PROGRESS: {p}% - {s}")
            )
        
        append_log(deployment_id, "✅ Deployer initialized successfully")
        while True:
            time.sleep(1)  # Keep process alive
            
    except Exception as e:
        import traceback
        print(traceback.print_exc())
        append_log(deployment_id, f"❌ Deployment failed: {str(e)}")
        raise e

# ---------------------------
# Deployment Process Manager
# ---------------------------
class DeploymentManager:
    def __init__(self):
        self.deployments = load_active_deployments()
        self._cleanup_zombies()
        self._update_statuses()
        
    def start_deployment(self, config):
        import uuid
        deployment_id = str(uuid.uuid4())[:8]
        # Start deployment process (assume deployment_runner_process is defined elsewhere)
        import multiprocessing
        process = multiprocessing.Process(
            target=deployment_runner_process,
            args=(deployment_id, config)
        )
        process.start()
        
        # Store only serializable metadata (do not store live objects)
        serializable_config = serialize_deployment_config(config)
        self.deployments[deployment_id] = {
            "pid": process.pid,
            "config": serializable_config,
            "status": "running",
            "created": dt.now().isoformat()
        }
        save_active_deployments(self.deployments)
        return deployment_id
    
    def stop_deployment(self, deployment_id):
        try:
            pid = self.deployments[deployment_id]["pid"]
            append_log(deployment_id, f"Sending SIGTERM to process {pid}")
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                append_log(deployment_id, f"Process {pid} not found; already terminated.")
                self.deployments.pop(deployment_id)
                save_active_deployments(self.deployments)
                return True

            time.sleep(5)  # Wait for graceful shutdown

            # Try to reap the process if it's in zombie state
            try:
                waited_pid, status = os.waitpid(pid, os.WNOHANG)
                if waited_pid == 0:
                    append_log(deployment_id, f"Process {pid} still running; sending SIGKILL.")
                    os.kill(pid, signal.SIGKILL)
                    time.sleep(2)
                    try:
                        waited_pid, status = os.waitpid(pid, os.WNOHANG)
                        if waited_pid != 0:
                            append_log(deployment_id, f"Process {pid} reaped with status {status} after SIGKILL.")
                        else:
                            append_log(deployment_id, f"Process {pid} still not reaped after SIGKILL.")
                    except Exception as ex:
                        append_log(deployment_id, f"Error waiting for process {pid} after SIGKILL: {ex}")
                else:
                    append_log(deployment_id, f"Process {pid} successfully reaped with status {status}.")
            except ChildProcessError:
                append_log(deployment_id, f"No child process exists for pid {pid}.")
            except Exception as ex:
                append_log(deployment_id, f"Error during waitpid: {ex}")

            self._cleanup_zombies()
            return True
        except Exception as e:
            append_log(deployment_id, f"Error in stop_deployment: {str(e)}")
            return False

    def _cleanup_zombies(self):
        """Remove terminated processes from deployment tracking."""
        for dep_id in list(self.deployments.keys()):
            pid = self.deployments[dep_id]["pid"]
            try:
                # os.waitpid with WNOHANG returns (0, 0) if the child hasn't been reaped,
                # otherwise, it returns (pid, status) and the child is reaped.
                waited_pid, status = os.waitpid(pid, os.WNOHANG)
                if waited_pid != 0:
                    append_log(dep_id, f"Process {pid} reaped during cleanup with status {status}.")
                    del self.deployments[dep_id]
            except ChildProcessError:
                append_log(dep_id, f"No child process exists for pid {pid} during cleanup.")
                del self.deployments[dep_id]
            except OSError:
                append_log(dep_id, f"Process {pid} no longer exists during cleanup.")
                del self.deployments[dep_id]
        save_active_deployments(self.deployments)
    
    def _update_statuses(self):
        """Check process statuses and update deployment status."""
        for dep_id, dep in list(self.deployments.items()):
            pid = dep["pid"]
            try:
                os.kill(pid, 0)  # Check if process exists
                dep["status"] = "running"
            except (OSError, ProcessLookupError):
                dep["status"] = "stopped"
        save_active_deployments(self.deployments)


# ---------------------------
# Enhanced UI Components
# ---------------------------
def deployment_status_badge(status):
    color = {
        "running": "green",
        "stopped": "red",
        "error": "orange"
    }.get(status, "gray")
    return f"<span style='color:{color};'>●</span> {status.capitalize()}"

def format_log_entry(log_line):
    if "ERROR" in log_line:
        return f"<div style='color: red;'>{log_line}</div>"
    elif "WARNING" in log_line:
        return f"<div style='color: orange;'>{log_line}</div>"
    return log_line

# ---------------------------
# Main Dashboard UI
# ---------------------------
st.title("🚀 Strategy Deployment Dashboard")
manager = DeploymentManager()

# New Deployment Form
with st.expander("New Deployment Configuration", expanded=True):

    # Get query parameters
    query_params = st.query_params
    preloaded_config = None
    if query_params != {}:
        backtest_uuid = query_params.get("backtest_uuid", None)
        
        if backtest_uuid:
            try:
                from backtest_engine.backtester import Backtester
                _, params = Backtester.load_backtest(backtest_uuid)
                preloaded_config = {
                    'market_name': params['market_name'],
                    'timeframe': params['timeframe'],
                    'symbol_list': params['symbol_list'],
                    'strategy_name': params['strategy_name'],
                    'strategy_params': params['strategy_params'],
                    'pair': params['pair'],
                    'init_cash': params['init_cash'],
                    'size' : params['size'],
                    'cash_sharing' : params['cash_sharing'],
                    'allow_partial' : params['allow_partial']
                }
                st.session_state['preloaded_params'] = params['strategy_params']
            except Exception as e:
                st.error(f"Error loading backtest: {str(e)}")
    
    if preloaded_config:
        st.success("✨ Deployment parameters automagically pre-filled from backtest!")
        st.markdown(f"**Loaded Backtest:** `{backtest_uuid}`")

    
    strategies = dynamic_strategy_loader()
    selected_strategy = st.selectbox(
        "Strategy", 
        options=list(strategies.keys()),
        index=list(strategies.keys()).index(preloaded_config['strategy_name']) if preloaded_config else 0
    )

    
    if selected_strategy:
        strategy_config = strategies[selected_strategy]
        params = strategy_config["params"]
        
        # Dynamic parameter inputs
        st.subheader("Strategy Parameters")
        param_values = {}
        for param, info in params.items():
            default_val = preloaded_config['strategy_params'].get(param, info["default"]) if preloaded_config else info["default"]
            if info["type"] == int:
                param_values[param] = st.number_input(
                    param.replace("_", " ").title(),
                    value=default_val,
                    min_value=info.get("min", 0),
                    step=info.get("step", 1)
                )
            elif info["type"] == float:
                param_values[param] = st.number_input(
                    param.replace("_", " ").title(),
                    value=default_val,
                    step=info.get("step", 0.001)
                )
            elif info["type"] == bool:
                param_values[param] = st.checkbox(
                    param.replace("_", " ").title(),
                    value=default_val
                )
            else:
                param_values[param] = st.text_input(
                    param.replace("_", " ").title(),
                    value=default_val
                )
        
        # Market Configuration
        st.subheader("Market Configuration")

        if preloaded_config:
            market_index = 0 if preloaded_config['market_name'] == "crypto_binance" else 1
            timeframe_index = ["15m", "1h", "4h", "1D",].index(preloaded_config['timeframe'])
        else:
            market_index = 0
            timeframe_index = 0
        
        market_name = st.selectbox(
            "Market", 
            options=["crypto_binance", "indian_equity"],
            index=market_index
        )
        timeframe = st.selectbox(
            "Timeframe", 
            options=["15m", "1h", "4h", "1D"],
            index=timeframe_index
        )
        
        # Asset Selection
        pair, asset_universe = asset_selection_widget(
            market_name, 
            timeframe,
            default_symbols=preloaded_config['symbol_list'] if preloaded_config else None,
            default_pair_type=preloaded_config.get('pair') if preloaded_config else None
        )

        if preloaded_config:
            st.session_state['preloaded_params'] = preloaded_config['strategy_params']
        else:
            st.session_state['preloaded_params'] = {}
        
        # OMS Configuration
        st.subheader("Order Management")
        oms_type = st.selectbox(
            "OMS Type", 
            options=["Telegram", "Zerodha", "Binance"]
        )
        oms_config = oms_config_widget(oms_type)
        
        # Scheduler Configuration
        scheduler = scheduler_config_widget()

        # Additional Deployment Settings
        st.subheader("Additional Deployment Settings")

        init_cash = st.number_input(
            "Initial Cash", 
            value=float(preloaded_config['init_cash']) if preloaded_config else 100000.0, 
            step=10.0
        )

        start_date = st.text_input(
            "Start Time (YYYY-MM-DD HH:MM:SS)", 
            value=str(pd.Timestamp.now() - pd.Timedelta(days=3))
        )

        size = st.number_input(
            "Position Size", 
            value=float(preloaded_config['size']) if preloaded_config else 1.0, 
            step=0.001
        )

        cash_sharing = st.checkbox(
            "Cash Sharing", 
            value=float(preloaded_config['cash_sharing']) if preloaded_config else False
        )

        allow_partial = st.checkbox(
            "Allow Partial Execution", 
            value=float(preloaded_config['allow_partial']) if preloaded_config else False
        )
        
        if st.button("Deploy Strategy"):
            if not asset_universe:
                st.error("Please select at least one asset")
                
            
            strategy_cls = strategy_config['func']
            try:
                strategy_instance = strategy_cls(**param_values)
            except Exception as e:
                st.error(f"Strategy initialization failed: {str(e)}")
                
            
            try:
                # TODO : Add more config details to fill when deploying
                config = {
                    "backtest_uuid": backtest_uuid if preloaded_config else None,
                    "strategy_name" : selected_strategy,
                    "strategy_object": strategy_instance,
                    "oms_type" : oms_type,
                    "strategy_params" : param_values,
                    "params": param_values,
                    "scheduler_type" : scheduler['type'],
                    "scheduler_interval" : scheduler['value'],
                    "deployer_params" : {
                        "init_cash" : init_cash,
                        "start_date" : start_date,
                        "size" : size,
                        "cash_sharing" : cash_sharing,
                        "allow_partial" : allow_partial,
                    },
                    "oms": {
                        "type": oms_type,
                        "config": oms_config
                    },
                    "market_params" : {
                        "market_name" : market_name,
                        "timeframe" : timeframe,
                        "pair" : pair,
                        "asset_universe" : asset_universe 
                    }
                }

                if oms_type == "Telegram":
                    config['oms']['config'] = {'chat_id': oms_config['chat_id']}
                elif oms_type == "Zerodha":
                    config['oms']['config'] = {
                        'userid': oms_config['userid'],
                        'password': oms_config['password'],
                        'totp': oms_config['totp']
                    }
                elif oms_type == "Binance":
                    config['oms']['config'] = {
                        'api_key': oms_config['api_key'],
                        'api_secret': oms_config['api_secret']
                    }
                
                deployment_id = manager.start_deployment(config)
                st.success(f"Deployment {deployment_id} started successfully!")
            
            except Exception as e:
                st.error(f"Deployment failed: {str(e)}")

    # Live Deployments Fragment
live_deployments(manager)


