# -------------------------------------------------------------------
# Imports
# -------------------------------------------------------------------

import streamlit as st
import pandas as pd
import inspect
import datetime
from datetime import date
import pickle
import time
from finstore.finstore import Finstore
from strategy.public.ema_strategy import get_ema_signals_wrapper
from strategy.strategy_registry import STRATEGY_REGISTRY
import plotly.graph_objects as go
import numpy as np
import os
from urllib.parse import urlencode
import json

# 📁 Directory structure for saving backtests
SAVE_DIR = "saved_backtests"
os.makedirs(SAVE_DIR, exist_ok=True)


# -------------------------------------------------------------------
# Cache functions to load data from Finstore
# -------------------------------------------------------------------
@st.cache_resource
def get_finstore_crypto(timeframe='4h'):
    return Finstore(market_name='crypto_binance', timeframe=timeframe)

@st.cache_resource
def get_finstore_indian_equity(timeframe='1d'):
    return Finstore(market_name='indian_equity', timeframe=timeframe)

@st.cache_resource
def get_finstore(market_name, timeframe, pair=''):
    return Finstore(market_name=market_name, timeframe=timeframe, pair=pair)

# -------------------------------------------------------------------
# Dummy Strategy Functions for Demonstration
# -------------------------------------------------------------------
def list_strategy_modules():
    """Return available strategy modules with their parameters"""
    strategy_dict = {}
    for strategy_name, strategy_details in STRATEGY_REGISTRY.items():
        strategy_dict[strategy_name] = strategy_details['class']

    return strategy_dict


def dummy_rsi_strategy(ohlcv_data, symbol_list, rsi_period=14, oversold=30, overbought=70):
    return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

def dummy_macd_strategy(ohlcv_data, symbol_list, fast=12, slow=26, signal=9):
    return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

# -------------------------------------------------------------------
# Asset Selection Helpers
# -------------------------------------------------------------------
def handle_crypto_selection(crypto_data):
    """Clean crypto selection with pair type filtering and search"""
    col1, col2 = st.columns([1, 3])
    
    with col1:
        pair_type = st.radio(
            "Pair Type:",
            options=["USDT", "BTC"],
            horizontal=True,
            help="Filter by trading pair type"
        )
        
    with col2:
        symbols = crypto_data.get(f"{pair_type} Pairs", [])
        search_query = st.text_input("Search crypto pairs:", key="crypto_search")
        filtered = [s for s in symbols if search_query.lower() in s.lower()]
        
        # Batch operations
        col1, col2 = st.columns(2)
        with col1:
            if st.button(f"Add all {pair_type} pairs", help="Add all filtered pairs"):
                add_symbols(filtered)
        with col2:
            if st.button(f"Clear {pair_type} selection", help="Remove all pairs of this type"):
                remove_symbols(filtered)
        
        # Symbol selection
        selected = st.multiselect(
            "Available pairs:",
            options=filtered,
            default=[s for s in filtered if s in st.session_state.selected_symbols],
            label_visibility="collapsed"
        )
        update_selection(selected, filtered)

def handle_equity_selection(indian_data, us_data):
    """Equity market selection with country grouping"""
    country = st.radio(
        "Market Region:",
        options=["India", "US"],
        horizontal=True
    )
    
    symbols = indian_data.get('NSE Equity', []) if country == "India" \
        else us_data.get('NASDAQ', []) + us_data.get('NYSE', [])
    
    search_query = st.text_input(f"Search {country} equities:", key=f"equity_search_{country}")
    filtered = [s for s in symbols if search_query.lower() in s.lower()]
    
    # Batch operations
    col1, col2 = st.columns(2)
    with col1:
        if st.button(f"Select all {country}"):
            add_symbols(filtered)
    with col2:
        if st.button(f"Clear {country}"):
            remove_symbols(filtered)
    
    # Symbol selection
    selected = st.multiselect(
        f"Select {country} equities:",
        options=filtered,
        default=[s for s in filtered if s in st.session_state.selected_symbols],
        label_visibility="collapsed"
    )
    update_selection(selected, filtered)

def handle_other_selection(commodities_data):
    """Commodities and other markets selection"""
    search_query = st.text_input("Search commodities:", key="comm_search")
    symbols = commodities_data.get('Metals', []) + commodities_data.get('Energy', [])
    filtered = [s for s in symbols if search_query.lower() in s.lower()]
    
    # Batch operations
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Select all commodities"):
            add_symbols(filtered)
    with col2:
        if st.button("Clear commodities"):
            remove_symbols(filtered)
    
    # Symbol selection
    selected = st.multiselect(
        "Select commodities:",
        options=filtered,
        default=[s for s in filtered if s in st.session_state.selected_symbols],
        label_visibility="collapsed"
    )
    update_selection(selected, filtered)


# -------------------------------------------------------------------
# Enhanced Asset Selection Components
# -------------------------------------------------------------------
def crypto_selection_widget(crypto_data):
    st.subheader("💰 Crypto Asset Selection")
    col1, col2 = st.columns([1, 3])
    
    with col1:
        pair_type = st.radio("Pair Type:", ["USDT", "BTC"], horizontal=True)
    
    with col2:
        symbols = crypto_data.get(f"{pair_type} Pairs", [])
        search_query = st.text_input("Search pairs:", key=f"crypto_search_{pair_type}")
        filtered = [s for s in symbols if search_query.lower() in s.lower()]
        
        col_a, col_b = st.columns(2)
        with col_a:
            if st.button(f"Add all {pair_type}", help="Add all filtered pairs"):
                add_symbols(filtered)
        with col_b:
            if st.button(f"Clear {pair_type}", help="Clear current selection"):
                remove_symbols(filtered)
        
        # Virtualized selection
        container = st.container()
        selected = container.multiselect(
            f"Select {pair_type} pairs:",
            options=filtered,
            default=[s for s in filtered if s in st.session_state.selected_symbols],
            label_visibility="collapsed"
        )
        update_selection(selected, filtered)

def equity_selection_widget(indian_data, us_data):
    st.subheader("📈 Equity Selection")
    country = st.radio("Market Region:", ["India", "US"], horizontal=True)
    
    symbols = indian_data.get('NSE Equity', []) if country == "India" \
        else us_data.get('NASDAQ', []) + us_data.get('NYSE', [])
    
    search_query = st.text_input(f"Search {country} equities:", key=f"equity_search_{country}")
    filtered = [s for s in symbols if search_query.lower() in s.lower()]
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button(f"Add all {country}"):
            add_symbols(filtered)
    with col2:
        if st.button(f"Clear {country}"):
            remove_symbols(filtered)
    
    container = st.container()
    selected = container.multiselect(
        f"Select {country} equities:",
        options=filtered,
        default=[s for s in filtered if s in st.session_state.selected_symbols],
        label_visibility="collapsed"
    )
    update_selection(selected, filtered)

def commodity_selection_widget(commodities_data):
    st.subheader("🛢️ Commodity Selection")
    search_query = st.text_input("Search commodities:", key="comm_search")
    symbols = commodities_data.get('Metals', []) + commodities_data.get('Energy', [])
    filtered = [s for s in symbols if search_query.lower() in s.lower()]
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Add all commodities"):
            add_symbols(filtered)
    with col2:
        if st.button("Clear commodities"):
            remove_symbols(filtered)
    
    container = st.container()
    selected = container.multiselect(
        "Select commodities:",
        options=filtered,
        default=[s for s in filtered if s in st.session_state.selected_symbols],
        label_visibility="collapsed"
    )
    update_selection(selected, filtered)


def display_selected_symbols():
    """Clean display of selected symbols"""
    selected = st.session_state.selected_symbols
    st.write(f"**Selected Assets:** {len(selected)}")
    
    if selected:
        # Show first 3 symbols + count of remaining
        display_text = ", ".join(selected[:3])
        if len(selected) > 3:
            display_text += f" (+{len(selected)-3} more)"
        st.caption(display_text)
        
        if st.button("Clear all selections", type="primary"):
            st.session_state.selected_symbols = []

def add_symbols(symbols):
    st.session_state.selected_symbols = list(set(st.session_state.selected_symbols + symbols))

def remove_symbols(symbols):
    st.session_state.selected_symbols = [s for s in st.session_state.selected_symbols if s not in symbols]

def update_selection(selected, full_list):
    """Handle multiselect updates"""
    for symbol in selected:
        if symbol not in st.session_state.selected_symbols:
            st.session_state.selected_symbols.append(symbol)
    for symbol in full_list:
        if symbol not in selected and symbol in st.session_state.selected_symbols:
            st.session_state.selected_symbols.remove(symbol)

def get_available_assets(timeframe=None):
    """Return hierarchical market structure with nested universes"""
    asset_groups = {}
    if not timeframe:
        return {'Please select timeframe first': []}

    try:
        # Get crypto pairs
        btc_pairs = get_finstore("crypto_binance", timeframe, pair="BTC").read.get_symbol_list()
        usdt_pairs = get_finstore("crypto_binance", timeframe, pair="USDT").read.get_symbol_list()
        asset_groups['Crypto'] = {
            'BTC Pairs': list(btc_pairs) if len(btc_pairs) > 0 else ['No BTC pairs'],
            'USDT Pairs': list(usdt_pairs) if len(usdt_pairs) > 0 else ['No USDT pairs']
        }
    except Exception as e:
        asset_groups['Crypto'] = {'Error': [f'Failed to load crypto data: {str(e)}']}

    try:
        nse_eq = get_finstore("indian_equity", timeframe, pair="").read.get_symbol_list()
        asset_groups['Indian Market'] = {
            'NSE Equity': list(nse_eq) if len(nse_eq) > 0 else ['No NSE equities']
        }
    except Exception as e:
        asset_groups['Indian Market'] = {'Error': [f'Failed to load Indian data: {str(e)}']}

    asset_groups.update({
        'US Market': {
            'NASDAQ': ['AAPL', 'TSLA', 'GOOG'],
            'NYSE': ['IBM', 'BA']
        },
        'Commodities': {
            'Metals': ['GOLD', 'SILVER'],
            'Energy': ['OIL', 'NATURALGAS']
        }
    })
    return asset_groups
# -------------------------------------------------------------------
# Strategy Backtester Page
# -------------------------------------------------------------------
def show_backtester_page():
    st.title("Strategy Backtester 🔧")
    st.markdown("---")
    
    # Initialize session state for selected symbols
    if 'selected_symbols' not in st.session_state:
        st.session_state.selected_symbols = []
    
    if "backtester_instance" not in st.session_state:
        st.session_state.backtester_instance = None
    
    if "initialized_strategy" not in st.session_state:
        st.session_state.initialized_strategy = None
    
    # 1. Timeframe Selection
    with st.container():
        col1, col2 = st.columns([1, 2])
        with col1:
            with st.expander("🕒 Time Configuration", expanded=True):
                timeframe = st.selectbox(
                    "Timeframe:",
                    options=["1D", "4H", "1H", "15m", "5m", "1m"],
                    index=2
                )
        
        with col2:
            with st.expander("📦 Strategy Module Selection", expanded=True):
                strategy_modules = list_strategy_modules()
                selected_module = st.selectbox("Select Strategy Module", options=list(strategy_modules.keys()))
    
    st.markdown("---")
    # 3. Asset Selection
    with st.expander("🌍 Asset Universe", expanded=True):
        with st.spinner("Loading Assets..."):
            asset_data = get_available_assets(timeframe)
            tab1, tab2, tab3 = st.tabs(["Crypto", "Equities", "Commodities"])
            
            with tab1:
                crypto_selection_widget(asset_data.get('Crypto', {}))
            with tab2:
                equity_selection_widget(asset_data.get('Indian Market', {}), 
                                    asset_data.get('US Market', {}))
            with tab3:
                commodity_selection_widget(asset_data.get('Commodities', {}))
            
            st.divider()
            display_selected_symbols()
    

    st.markdown("---")
    # 4. Strategy Parameters
    with st.expander("⚙️ Strategy Parameters", expanded=True):
        strategy_func = strategy_modules[selected_module]
        sig = inspect.signature(strategy_func.__init__)
        params = {}
        # Skip the first two parameters (ohlcv_data and symbol_list)
        for param in list(sig.parameters.values())[1:]:
            if param.annotation == int:
                val = st.number_input(
                    param.name,
                    value=param.default if param.default != inspect.Parameter.empty else 0,
                    step=1
                )
            elif param.annotation == float:
                val = st.number_input(
                    param.name,
                    value=param.default if param.default != inspect.Parameter.empty else 0.0,
                    step=0.000001
                )
            else:
                val = st.text_input(
                    param.name,
                    value=str(param.default) if param.default != inspect.Parameter.empty else ""
                )
            params[param.name] = val
    
    st.markdown("---")
    # 5. Backtest Configuration
    with st.expander("📅 Backtest Settings", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            start_date = st.date_input("Start Date", value=date(2023, 1, 1))
        with col2:
            end_date = st.date_input("End Date", value=date(2026, 1, 1))
        
        init_cash = st.number_input("Initial Capital", value=100000)
        fees = st.number_input("Trading Fees (%)", step=0.0001, value=0.0005, format="%.6f")
        slippage = st.number_input("Slippage (%)", step=0.0001, value=0.001, format="%.6f")
        size = st.number_input("Size (%)", step=0.01, value=0.01, format="%.6f")
        # Convert the string selection to a boolean
        allow_partial_str = st.selectbox(
            "Allow Partial ? (Usually set True for crypto):",
            options=["True", "False"],
            index=0
        )
        allow_partial = True if allow_partial_str == "True" else False
        cash_sharing_str = st.selectbox(
            "Allow Cash Sharing ? (All assets will share the same cash):",
            options=["True", "False"],
            index=0
        )
        cash_sharing = True if cash_sharing_str == "True" else False

    # 6. Run Backtest
    if st.button("🚀 Run Backtest", use_container_width=True):
        if not st.session_state.selected_symbols:
            st.error("Please select at least one asset!")
            return
        
        progress_bar = st.progress(0)
        status_text = st.empty()

        def update_progress(progress: int, status: str) -> None:
            status_text.markdown(status)
            progress_bar.progress(progress)
            if progress >= 100:
                progress_bar.empty()
                status_text.empty()
        
        try:
            update_progress(0,"Importing Libraries...")
            from backtest_engine.backtester import Backtester
            update_progress(10, "📂 Loading market data...")
            
            strategy_instance = strategy_func(**params)
            
            backtester = Backtester(
                market_name='crypto_binance',
                symbol_list=st.session_state.selected_symbols,
                timeframe=timeframe,
                strategy_object=strategy_instance,
                strategy_type='multi',
                start_date=pd.Timestamp(start_date),
                end_date=pd.Timestamp(end_date),
                init_cash=init_cash,
                fees=fees,
                slippage=slippage,
                size=size,
                cash_sharing=cash_sharing,
                allow_partial=allow_partial,
                progress_callback=update_progress,
                pair='BTC'
            )
            
            pf = backtester.portfolio
            
            update_progress(100, "✅ Backtest completed successfully!")
            
            st.session_state.backtester_instance = backtester
            st.session_state.initialized_strategy = strategy_instance
            st.success("✅ Backtest completed successfully!")
            
        except Exception as e:
            progress_bar.empty()
            st.error(f"❌ Backtest failed: {str(e)}")
            import traceback
            print(traceback.print_exc())
            print(e)

        # Assuming 'pf' is the portfolio object generated from your backtest

        with st.spinner("Loading Backtest statistics..."):

            st.subheader("📊 Detailed Portfolio Statistics")
            stats_df = pf.stats().to_frame(name='Value')

            # Convert Timedelta values to strings
            stats_df["Value"] = stats_df["Value"].apply(lambda x: str(x) if isinstance(x, pd.Timedelta) else x)

            st.dataframe(stats_df)

            # --- Equity (PNL) Curve ---
            st.subheader("📈 Equity (PNL) Curve")
            fig_pnl = go.Figure()
            fig_pnl.add_trace(go.Scatter(
                x=pf.value().index, 
                y=pf.value(),
                mode='lines',
                name="Portfolio Value"
            ))
            fig_pnl.update_layout(
                yaxis_title="Portfolio Value",
                title="Equity Curve",
                yaxis_type="log" if pf.value().max() > 10000 else "linear"  # Log scale for large values
            )
            st.plotly_chart(fig_pnl)

            # --- Cumulative Returns ---
            st.subheader("📈 Cumulative Returns")
            fig_cum = go.Figure()
            fig_cum.add_trace(go.Scatter(
                x=pf.cumulative_returns().index, 
                y=pf.cumulative_returns(),
                mode='lines',
                name="Cumulative Returns"
            ))
            fig_cum.update_layout(
                yaxis_title="Cumulative Returns",
                title="Cumulative Returns Curve",
                yaxis_type="log" if pf.cumulative_returns().max() > 10 else "linear"  # Log scale for large movements
            )
            st.plotly_chart(fig_cum)

            # Returns Overview (pf.returns is a property, not a method)
            st.subheader("📊 Returns Overview")
            returns_series = pf.returns()
            returns_df = returns_series.to_frame(name="Returns")
            st.dataframe(returns_df)


            # Trade History
            st.subheader("📝 Trade History")
            st.dataframe(pf.trades.records_readable)
        

        with st.spinner("Loading Advanced statistic plots..."):

            # Risk-adjusted Metrics: Sharpe & Sortino Ratios
            sharpe_ratio = pf.sharpe_ratio()
            sortino_ratio = pf.sortino_ratio()
            st.metric(label="📈 Sharpe Ratio", value=f"{int(sharpe_ratio):.2f}")
            st.metric(label="📈 Sortino Ratio", value=f"{int(sortino_ratio):.2f}")

            # Benchmark Comparison (if available)
            if hasattr(pf, 'benchmark_cumulative_returns'):
                st.subheader("📊 Benchmark vs Portfolio Performance")
                st.line_chart(pf.cumulative_returns())
        

    # 📌 Save Portfolio with Metadata
    st.subheader("💾 Save Backtest Portfolio")
    save_filename = st.text_input("Enter filename to save (without extension):", value=f"{selected_module}_{timeframe}_{date.today()}")

    if st.button("Save Portfolio"):
        if st.session_state.backtester_instance is None:
            st.error("❌ No portfolio to save! Run a backtest first.")
        else:
            try:
                st.session_state.backtester_instance.save_backtest(save_name = save_filename)

                st.success(f"✅ Portfolio saved successfully as database/backtest/{save_filename}")
            except Exception as e:
                st.error(f"❌ Error while saving: {e}")
                import traceback
                print(traceback.print_exc())



    # 🔄 Load Previously Backtested Portfolio
    with st.expander("📂 Load Previous Backtest", expanded=False):

        with st.spinner("Loading backtests..."):

            from backtest_engine.backtester import Backtester
            # Fetch available backtests
            backtests = Backtester.list_backtests()

            if not backtests:
                st.info("No saved backtests found. Run and save a backtest first.")
            else:
                selected_backtest = st.selectbox("Select a backtest to view:", list(backtests.keys()))

                if selected_backtest:
                    params = backtests[selected_backtest]

                    col1, col2 = st.columns(2)

                    with col1:
                        st.write(f"**Strategy Name:** {params['strategy_name']}")
                        st.write(f"**Market Name:** {params['market_name']}")
                        st.write(f"**Timeframe:** {params['timeframe']}")
                        st.write(f"**Symbols:** {', '.join(params['symbol_list'])}")
                        st.write(f"**Trading Pair:** {params['pair']}")
                        st.write(f"**Start Date:** {params['start_date']}")
                        st.write(f"**End Date:** {params['end_date']}")

                    with col2:
                        st.write(f"**Initial Cash:** ${params['init_cash']:,.2f}")
                        st.write(f"**Trading Fees:** {params['fees'] * 100:.4f}%")
                        st.write(f"**Slippage:** {params['slippage'] * 100:.4f}%")
                        st.write(f"**Allow Partial Orders:** {params['allow_partial']}")
                        st.write("**Strategy Parameters:**")
                        st.json(params["strategy_params"])

                    # 📊 Performance Metrics
                    st.subheader("📊 Performance Metrics")
                    col1, col2, col3 = st.columns(3)
                    col1.metric(label="📈 Returns", value=f"{params['performance']['returns']:.2%}")
                    col2.metric(label="📈 Sharpe Ratio", value=f"{params['performance']['sharpe_ratio']:.2f}")
                    col3.metric(label="📉 Max Drawdown", value=f"{params['performance']['max_drawdown']:.2%}")
                    
                    deploy_col1, deploy_col2 = st.columns(2)
                    # 🔄 Load Backtest Button
                    if deploy_col1.button("🔍 Load Portfolio & Stats"):
                        with st.spinner("Loading backtest..."):
                            pf, _ = Backtester.load_backtest(selected_backtest)  # Load portfolio

                        # ✅ Success message
                        st.success(f"Successfully loaded backtest: {selected_backtest}")

                        # 📊 Display Portfolio Statistics
                        st.subheader("📊 Portfolio Statistics")
                        stats_df = pf.stats().to_frame(name="Value")

                        # Convert Timedelta values to readable format
                        stats_df["Value"] = stats_df["Value"].apply(lambda x: str(x) if isinstance(x, pd.Timedelta) else x)

                        st.dataframe(stats_df)

                        # --- 📈 Equity (PNL) Curve ---
                        st.subheader("📈 Equity (PNL) Curve")
                        fig_pnl = go.Figure()
                        fig_pnl.add_trace(go.Scatter(
                            x=pf.value().index, 
                            y=pf.value(),
                            mode='lines',
                            name="Portfolio Value"
                        ))
                        fig_pnl.update_layout(
                            yaxis_title="Portfolio Value",
                            title="Equity Curve",
                            yaxis_type="log" if pf.value().max() > 10000 else "linear"
                        )
                        st.plotly_chart(fig_pnl)

                        # --- 📈 Cumulative Returns ---
                        st.subheader("📈 Cumulative Returns")
                        fig_cum = go.Figure()
                        fig_cum.add_trace(go.Scatter(
                            x=pf.cumulative_returns().index, 
                            y=pf.cumulative_returns(),
                            mode='lines',
                            name="Cumulative Returns"
                        ))
                        fig_cum.update_layout(
                            yaxis_title="Cumulative Returns",
                            title="Cumulative Returns Curve",
                            yaxis_type="log" if pf.cumulative_returns.max() > 10 else "linear"
                        )
                        st.plotly_chart(fig_cum)

                        # 📊 Returns Overview
                        st.subheader("📊 Returns Overview")
                        returns_df = pf.returns.to_frame(name="Returns")
                        st.dataframe(returns_df)

                        # 📑 Trade History
                        st.subheader("📝 Trade History")
                        st.dataframe(pf.trades.records_readable)

                        # 🔍 Advanced Metrics & Risk Analysis
                        with st.spinner("Loading Advanced Statistics..."):

                            # 📈 Risk-adjusted Metrics: Sharpe & Sortino Ratios
                            sharpe_ratio = pf.sharpe_ratio()
                            sortino_ratio = pf.sortino_ratio()
                            st.metric(label="📈 Sharpe Ratio", value=f"{sharpe_ratio:.2f}")
                            st.metric(label="📈 Sortino Ratio", value=f"{sortino_ratio:.2f}")

                            # 📊 Benchmark Comparison (if available)
                            if hasattr(pf, 'benchmark_cumulative_returns'):
                                st.subheader("📊 Benchmark vs Portfolio Performance")
                                st.line_chart(pf.cumulative_returns())

                    if deploy_col2.button("🚀 Deploy Strategy"):
                        # Get backtest UUID and parameters
                        backtest_uuid = selected_backtest
                        params = backtests[selected_backtest]
                        
                        # Generate URL parameters for deployment dashboard
                        deploy_params = {
                            'backtest_uuid': backtest_uuid
                        }
                        
                        query_string = urlencode(deploy_params)

                        js = f"""
                                <script>
                                    // Get the full URL
                                    var fullUrl = window.location.href;

                                    // Extract base path by removing everything after the last '/'
                                    var basePath = fullUrl.substring(0, fullUrl.lastIndexOf('/'));

                                    // Construct the deployment URL
                                    var deployUrl = basePath + "/strategy_deployment?{query_string}";

                                    // Open in a new tab
                                    window.open(deployUrl, "_blank");
                                </script>
                            """

                        # Execute JavaScript in Streamlit
                        st.components.v1.html(js, height=0)


# Run the page
show_backtester_page()