import agent_tools
import streamlit as st

st.title("HR Assistant - Amazon Bedrock Multi-Agents") # Title of the application


st.sidebar.markdown(
    "This app shows an Multi-Agents HR Assistant Chatbot powered by Amazon Bedrock Agents to answer questions."
)
clear_button = st.sidebar.button("Clear Conversation", key="clear")
# reset sessions state on clear
if clear_button:
    st.session_state.chat_history = []
    st.session_state.session_id = agent_tools.generate_random_15digit()


if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
    st.session_state.session_id = agent_tools.generate_random_15digit()

for message in st.session_state.chat_history:
    with st.chat_message(message["role"]):
        st.markdown(message["text"])

if prompt := st.chat_input("How can I help??"):
    with st.chat_message('user'):
        st.markdown(prompt)
    st.session_state.chat_history.append({"role":'user', "text":prompt})
    
    result = agent_tools.invoke_bedrock_agent(
        prompt, st.session_state.session_id
    )
    response = result["text"]
    
    with st.chat_message('assistant'):
        st.markdown(response)
    st.session_state.chat_history.append({"role":'assistant', "text": response})
