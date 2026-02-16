
import os
import tempfile
import yaml
from app.agent import SignalAgent
from app.utils.exceptions import ConstraintViolation

def check_integration():
    # 1. Create dummy constraint pack
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump({
            "scope": "integration_test",
            "disallowed_phrases": ["forbidden_magic_word"]
        }, f)
        pack_path = f.name

    try:
        # 2. Initialize Agent (Stubbed provider in agent.py will return input usually, 
        # but agent.py uses StubProvider which returns "Stub response for: ...")
        # We need to ensure the output contains the forbidden word to trigger failure,
        # OR we rely on the input reflection if StubProvider does that.
        # Looking at agent.py: StubProvider() is default.
        # Let's inspect StubProvider behavior if possible, or just mock the provider.
        
        agent = SignalAgent()
        
        # Inject a mock provider to ensure deterministic output containing forbidden word
        class MockProvider:
            def call(self, model, prompt):
                return f"Constraint violated: {prompt}"
        
        from app.agent import AgentConfig
        config = AgentConfig(models=("mock:model",))
        # Re-instantiate agent with config
        agent = SignalAgent(config=config)
        agent.providers["mock:model"] = MockProvider()
        
        print("Running generation with forbidden word...")
        try:
            agent.generate("forbidden_magic_word", constraint_pack_path=pack_path)
            print("FAILURE: Agent did not raise ConstraintViolation")
            exit(1)
        except ConstraintViolation as e:
            print(f"SUCCESS: Caught expected violation: {e}")
            
        # 3. Test Pass Case
        print("Running valid generation...")
        agent.generate("safe_word", constraint_pack_path=pack_path)
        print("SUCCESS: Valid generation passed")
        
    finally:
        if os.path.exists(pack_path):
            os.remove(pack_path)

if __name__ == "__main__":
    check_integration()
