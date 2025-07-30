import streamlit as st
import pandas as pd
import numpy as np

# --- Constants and Default Values ---
DEFAULT_REFUND_RATE = 0.03
DEFAULT_PLATFORM_FEE_RATE = 0.04
DEFAULT_MERCH_UNIT_COST = 20.00
DEFAULT_PRICE_INCREASE_CAP = 5.00

# --- Core Calculation Logic (Functions remain the same) ---

def _calculate_multi_tier_prices(tier_definitions, fixed_costs_event,
                                 sponsor_allocation_event, event_total_catering_cost,
                                 sum_of_sales_for_active_tiers,
                                 event_refund_rate, event_platform_fee_rate):
    priced_tiers = []
    catering_per_head = event_total_catering_cost / sum_of_sales_for_active_tiers if sum_of_sales_for_active_tiers > 0 else 0
    gap_to_cover_by_tickets = fixed_costs_event - sponsor_allocation_event

    for tier_def_original in tier_definitions:
        tier_def = tier_def_original.copy()
        tier_def['v_calc'] = catering_per_head + tier_def['merch_cost']
        tier_priced_data = {**tier_def}

        if tier_def['sold'] <= 0:
            tier_priced_data.update({'P_net': float('nan'), 'P_gross': float('nan')})
            if 'v_calc' in tier_priced_data: del tier_priced_data['v_calc']
            priced_tiers.append(tier_priced_data)
            continue
        
        tier_gap_share = 0
        if sum_of_sales_for_active_tiers > 0:
            tier_gap_share = gap_to_cover_by_tickets * (tier_def['sold'] / sum_of_sales_for_active_tiers)
        
        denominator_p_net = (1 - event_refund_rate) * tier_def['sold']
        P_net = tier_def['v_calc'] + (tier_gap_share / denominator_p_net) if denominator_p_net != 0 else float('inf')
        
        denominator_p_gross = (1 - event_platform_fee_rate)
        P_gross = P_net / denominator_p_gross if denominator_p_gross != 0 else float('inf')
        
        tier_priced_data.update({'P_net': P_net, 'P_gross': P_gross})
        if 'v_calc' in tier_priced_data: del tier_priced_data['v_calc']
        priced_tiers.append(tier_priced_data)
        
    return priced_tiers

def plan_event_scenarios(event_name: str,
                         event_fixed_costs: float, event_total_catering_cost: float,
                         total_expected_attendees_overall: int,
                         merch_option: str, 
                         merch_unit_cost: float,
                         expected_merch_tickets_sold_input: int,
                         last_year_regular_price: float,
                         last_year_merch_price: float,
                         sponsor_allocations_to_test: list,
                         event_refund_rate: float,
                         event_platform_fee_rate: float,
                         price_increase_cap: float):
    scenarios_summary = []

    for s_alloc_raw in sponsor_allocations_to_test:
        try:
            s_alloc = float(s_alloc_raw)
        except ValueError:
            st.warning(f"Invalid sponsor allocation value skipped: {s_alloc_raw}")
            continue
        if s_alloc < 0: continue

        current_scenario_data = {
            'event_name': event_name, 'sponsor_allocation_tested': s_alloc,
            'P_gross_regular': None, 'is_too_expensive_regular': None,
            'P_gross_merch': None, 'is_too_expensive_merch': None,
            'notes': ""
        }

        tier_definitions_for_calc = []
        reg_sold_calc = 0
        merch_sold_calc = 0

        if merch_option == "No Merch":
            reg_sold_calc = total_expected_attendees_overall
        elif merch_option == "Bundled Merch (for all tickets)":
            reg_sold_calc = total_expected_attendees_overall
        elif merch_option == "Optional Merch Tickets (separate prices)":
            if expected_merch_tickets_sold_input > total_expected_attendees_overall:
                current_scenario_data['notes'] = "Input Error: Merch tickets > total attendees."
                scenarios_summary.append(current_scenario_data)
                continue
            merch_sold_calc = expected_merch_tickets_sold_input
            reg_sold_calc = total_expected_attendees_overall - merch_sold_calc
        
        if merch_option == "No Merch":
            if reg_sold_calc > 0:
                tier_definitions_for_calc.append({'name': "Regular", 'sold': reg_sold_calc, 'merch_cost': 0, 'last_year_price': last_year_regular_price})
        elif merch_option == "Bundled Merch (for all tickets)":
            if reg_sold_calc > 0:
                tier_definitions_for_calc.append({'name': "Bundled", 'sold': reg_sold_calc, 'merch_cost': merch_unit_cost, 'last_year_price': last_year_regular_price})
        elif merch_option == "Optional Merch Tickets (separate prices)":
            if reg_sold_calc > 0:
                tier_definitions_for_calc.append({'name': "Regular", 'sold': reg_sold_calc, 'merch_cost': 0, 'last_year_price': last_year_regular_price})
            if merch_sold_calc > 0:
                tier_definitions_for_calc.append({'name': "Merch-Inclusive", 'sold': merch_sold_calc, 'merch_cost': merch_unit_cost, 'last_year_price': last_year_merch_price})
        
        sum_of_sales_for_active_tiers = sum(tier['sold'] for tier in tier_definitions_for_calc)

        if total_expected_attendees_overall == 0:
            current_scenario_data['notes'] = "Attendees is 0; cannot price tickets."
        
        if current_scenario_data['notes']:
            scenarios_summary.append(current_scenario_data)
            continue
        
        priced_tiers_results = _calculate_multi_tier_prices(
            tier_definitions_for_calc, event_fixed_costs, s_alloc,
            event_total_catering_cost, sum_of_sales_for_active_tiers,
            event_refund_rate, event_platform_fee_rate
        )

        for tier_result in priced_tiers_results:
            P_gross = tier_result['P_gross']
            is_too_expensive = None
            ly_price_for_tier = tier_result.get('last_year_price')
            if pd.notnull(P_gross) and np.isfinite(P_gross) and pd.notnull(ly_price_for_tier):
                is_too_expensive = P_gross > (ly_price_for_tier + price_increase_cap)

            if tier_result['name'] in ["Regular", "Bundled"]:
                current_scenario_data['P_gross_regular'] = P_gross
                current_scenario_data['is_too_expensive_regular'] = is_too_expensive
            elif tier_result['name'] == "Merch-Inclusive":
                current_scenario_data['P_gross_merch'] = P_gross
                current_scenario_data['is_too_expensive_merch'] = is_too_expensive
        
        scenarios_summary.append(current_scenario_data)
    return scenarios_summary

# --- Streamlit App UI ---
st.set_page_config(layout="wide", page_title="Event Ticket Price Calculator")
st.title("🎟️ Event Ticket Price Calculator")

# --- Initialisation ---
if 'current_scenarios' not in st.session_state:
    st.session_state.current_scenarios = []
    st.session_state.merch_option_ui = "No Merch"

# --- Main Page: Event Planning ---
st.header("📊 Step 1: Enter Event Details")
st.write("Use this form to calculate break-even ticket prices for an event under different subsidy scenarios.")

with st.form(key="event_planning_form"):
    st.subheader("Event Details")
    event_name_form = st.text_input("Event Name", "My Awesome Event", help="A descriptive name for your event.")
    
    col1, col2 = st.columns(2)
    with col1:
        total_expected_attendees_overall_form = st.number_input("Total Expected Attendees", min_value=0, value=180, step=5, help="Your best guess for the total number of people who will buy a ticket.")
        last_year_regular_price_form = st.number_input("Last Year's Regular Ticket Price ($)", min_value=0.0, value=30.0, step=1.0, help="The price of a standard ticket for this event last year. Used to check if the new price is too high.")
    with col2:
        event_fixed_costs_form = st.number_input("Event Fixed Costs ($)", min_value=0.0, value=5000.0, step=100.0, help="Costs that don't change with the number of attendees (e.g., venue hire, AV, prize money).")
        # --- MODIFIED ---
        event_total_catering_cost_input = st.number_input("Total Catering Budget ($)", min_value=0.0, value=4000.0, step=50.0, help="The total budget for food and drinks. This is overridden by the detailed calculation below if used.")
    
    # --- ADDED: Detailed Catering Calculation ---
    st.subheader("Catering Calculation (Optional)")
    st.write("For events like hackathons with multiple meals, use this to calculate the total catering budget. If used, this overrides the 'Total Catering Budget' field above.")
    
    cat_col1, cat_col2 = st.columns(2)
    with cat_col1:
        cost_per_meal_person_form = st.number_input("Cost Per Meal Per Person ($)", min_value=0.0, value=0.0, step=0.50, help="The cost of a single meal (e.g., lunch) for one person.")
    with cat_col2:
        num_meal_occasions_form = st.number_input("Number of Meal Occasions", min_value=0, value=0, step=1, help="The number of times you will provide food (e.g., for a weekend hackathon, this might be 5 for Fri dinner, Sat breakfast/lunch/dinner, Sun breakfast).")


    st.subheader("Merchandise Options")
    st.session_state.merch_option_ui = st.radio(
        "Will this event have merchandise?",
        ("No Merch", "Bundled Merch (for all tickets)", "Optional Merch Tickets (separate prices)"),
        key="merch_option_radio_key",
        horizontal=True,
        help="Choose how merchandise will be handled. Merch cost is part of the per-attendee variable cost."
    )

    merch_unit_cost_submit = 0.0
    expected_merch_tickets_sold_submit = 0
    last_year_merch_price_submit = 0.0

    if st.session_state.merch_option_ui == "Bundled Merch (for all tickets)":
        merch_unit_cost_submit = st.number_input("Merch Cost Per Unit ($)", min_value=0.0, value=DEFAULT_MERCH_UNIT_COST, step=1.0, help="The cost to produce one unit of the merchandise (e.g., one t-shirt).")
    elif st.session_state.merch_option_ui == "Optional Merch Tickets (separate prices)":
        col_m1, col_m2, col_m3 = st.columns(3)
        with col_m1:
            merch_unit_cost_submit = st.number_input("Merch Cost Per Unit ($)", min_value=0.0, value=DEFAULT_MERCH_UNIT_COST, step=1.0, help="The cost to produce one unit of the merchandise.")
        with col_m2:
            expected_merch_tickets_sold_submit = st.number_input("Expected Merch Ticket Sales", min_value=0, max_value=total_expected_attendees_overall_form, value=50, step=1, help="How many attendees you expect to buy the more expensive merch-inclusive ticket.")
        with col_m3:
            default_ly_merch_price = last_year_regular_price_form + merch_unit_cost_submit
            last_year_merch_price_submit = st.number_input("Last Year's Merch Ticket Price ($)", min_value=0.0, value=default_ly_merch_price, step=1.0, help="If a similar merch ticket existed last year, what was its price?")

    st.subheader("Sponsorship Scenarios")
    sponsor_allocations_str_form = st.text_input(
        "Sponsorship / UQCS Subsidy to Test ($)", "0, 500, 1000, 2000, 3000",
        help="Enter different amounts of subsidy from UQCS to see how it affects ticket prices. Separate values with commas."
    )
    
    with st.expander("Advanced Settings"):
        st.markdown("These are the financial assumptions for calculations.")
        default_refund_ui = st.slider("Refund Rate (φ) (%)", 0, 20, int(DEFAULT_REFUND_RATE*100), help="The percentage of tickets you expect to be refunded.") / 100.0
        default_platform_fee_ui = st.slider("Platform Fee (f) (%)", 0, 20, int(DEFAULT_PLATFORM_FEE_RATE*100), help="The fee charged by the ticketing platform as a percentage of the ticket price.") / 100.0
        default_price_cap_ui = st.number_input("Max Price Increase Cap ($)", min_value=0.0, value=DEFAULT_PRICE_INCREASE_CAP, step=1.0, help="The maximum you want the ticket price to increase compared to last year's price.")

    calculate_scenarios_button = st.form_submit_button("📊 Calculate Prices")

# --- Process and Display Scenarios ---
if calculate_scenarios_button:
    # --- ADDED: Logic to handle optional catering calculation ---
    if cost_per_meal_person_form > 0 and num_meal_occasions_form > 0:
        # Use the detailed calculation
        final_catering_cost = cost_per_meal_person_form * total_expected_attendees_overall_form * num_meal_occasions_form
        st.success(f"Using detailed catering calculation: Total Budget = ${final_catering_cost:,.2f}")
    else:
        # Fall back to the main budget field
        final_catering_cost = event_total_catering_cost_input

    merch_option_for_calc = st.session_state.merch_option_ui

    if merch_option_for_calc == "Optional Merch Tickets (separate prices)" and expected_merch_tickets_sold_submit > total_expected_attendees_overall_form:
        st.error("Error: Expected Merch Ticket Sales cannot be greater than Total Expected Attendees.")
        st.session_state.current_scenarios = []
    else:
        try:
            sponsor_allocations_list = [s.strip() for s in sponsor_allocations_str_form.split(',') if s.strip()]
            if not sponsor_allocations_list:
                st.error("Please enter at least one subsidy amount to test.")
                st.session_state.current_scenarios = []
            elif not all(s.replace('.', '', 1).lstrip('-').replace('.', '', 1).isdigit() for s in sponsor_allocations_list if s):
                 st.error("Please enter valid comma-separated numbers for subsidy amounts.")
                 st.session_state.current_scenarios = []
            else:
                st.session_state.current_scenarios = plan_event_scenarios(
                    event_name=event_name_form, event_fixed_costs=event_fixed_costs_form,
                    event_total_catering_cost=final_catering_cost,  # MODIFIED
                    total_expected_attendees_overall=total_expected_attendees_overall_form,
                    merch_option=merch_option_for_calc,
                    merch_unit_cost=merch_unit_cost_submit,
                    expected_merch_tickets_sold_input=expected_merch_tickets_sold_submit,
                    last_year_regular_price=last_year_regular_price_form,
                    last_year_merch_price=last_year_merch_price_submit,
                    sponsor_allocations_to_test=sponsor_allocations_list,
                    event_refund_rate=default_refund_ui,
                    event_platform_fee_rate=default_platform_fee_ui,
                    price_increase_cap=default_price_cap_ui
                )
        except Exception as e:
            st.error(f"An error occurred during scenario calculation: {e}")
            st.exception(e)
            st.session_state.current_scenarios = []

if 'current_scenarios' in st.session_state and st.session_state.current_scenarios:
    st.header("📈 Step 2: Review Price Scenarios")
    current_event_name_display = st.session_state.current_scenarios[0]['event_name']
    
    st.info(f"""
    This table shows the calculated ticket prices for **{current_event_name_display}**. 
    Each row represents a scenario where UQCS contributes a different amount of subsidy to help cover event costs. 
    The more subsidy UQCS provides, the lower the ticket price can be to break even.
    """)

    scenarios_df_display = pd.DataFrame(st.session_state.current_scenarios)
    
    column_rename_map = {
        'sponsor_allocation_tested': 'UQCS Subsidy ($)',
        'P_gross_regular': 'Regular/Bundled Price ($)',
        'is_too_expensive_regular': 'Price Too High?',
        'P_gross_merch': 'Merch Ticket Price ($)',
        'is_too_expensive_merch': 'Merch Price Too High?',
        'notes': 'Notes'
    }
    
    display_cols_base = ['sponsor_allocation_tested', 'P_gross_regular', 'is_too_expensive_regular']
    if st.session_state.merch_option_ui == "Optional Merch Tickets (separate prices)":
        display_cols_base.extend(['P_gross_merch', 'is_too_expensive_merch'])
    display_cols_base.append('notes')

    display_cols_final = [col for col in display_cols_base if col in scenarios_df_display.columns]
    display_df = scenarios_df_display[display_cols_final].rename(columns=column_rename_map)

    def format_price_display(x):
        if pd.isnull(x): return "N/A"
        if np.isinf(x): return "Error"
        return f"${x:,.2f}"
    
    def format_bool_yes_no_na(x):
        if pd.isnull(x): return "N/A"
        return "⚠️ Yes" if x else "No"

    st.dataframe(
        display_df.style.format({
            "UQCS Subsidy ($)": "${:,.2f}",
            "Regular/Bundled Price ($)": format_price_display,
            "Merch Ticket Price ($)": format_price_display,
            "Price Too High?": format_bool_yes_no_na,
            "Merch Price Too High?": format_bool_yes_no_na,
        }),
        hide_index=True, use_container_width=True
    )