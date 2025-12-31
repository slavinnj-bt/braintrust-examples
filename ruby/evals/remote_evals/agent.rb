# encoding: utf-8
# frozen_string_literal: true

# config/initializers/ruby_llm.rb (in Rails) or at the start of your script
require 'ruby_llm'
require 'json'

# for tracing
require "braintrust"
require "opentelemetry/sdk"

# Set default encoding
Encoding.default_external = Encoding::UTF_8
Encoding.default_internal = Encoding::UTF_8

# Weather tool and chat instance based on examples in ruby_llm:
# https://rubyllm.com/tools/
class Weather < RubyLLM::Tool
  description "Gets current weather for a location"

  params do  # the params DSL is only available in v1.9+. older versions should use the param helper instead
    string :latitude, description: "Latitude (e.g., 52.5200)"
    string :longitude, description: "Longitude (e.g., 13.4050)"
  end

  def execute(latitude:, longitude:)
    url = "https://api.open-meteo.com/v1/forecast?latitude=#{latitude}&longitude=#{longitude}&current=temperature_2m,wind_speed_10m"

    response = Faraday.get(url)
    data = JSON.parse(response.body)
  rescue => e
    { error: e.message }
  end
end

RubyLLM.configure do |config|
  config.openai_api_key = ENV.fetch('OPENAI_API_KEY', nil)
  config.anthropic_api_key = ENV.fetch('ANTHROPIC_API_KEY', nil)
end

Braintrust.init(
  blocking_login: false,
  default_project: ENV.fetch('BRAINTRUST_PARENT', nil)
)
Braintrust::Trace::Contrib::Github::Crmne::RubyLLM.wrap
tracer = OpenTelemetry.tracer_provider.tracer("weather-agent")

# Grabbing the remote eval params from the Python subprocess
model = ARGV[0]
location = ARGV[1]
system_prompt = ARGV[2]

begin
  # Create a root span to nest all chat and tool operations
  tracer.in_span("weather_agent", kind: :client) do |root_span|

    # Create a chat instance
    chat = RubyLLM.chat(model: model) # Use a model that supports tools

    # Set the initial instruction
    chat.with_instructions system_prompt

    # Instantiate your tool if it requires arguments, otherwise use the class
    weather_tool = Weather.new

    # Add the tool(s) to the chat
    chat.with_tool(weather_tool)

    # Ask the question - RubyLLM instrumentation will automatically trace this
    question = "What's the current weather like in " + location
    response = chat.ask question

    root_span.set_attribute("response_length", response.content.length)

    # Output JSON to stdout
    output = {
      result: response.content,
      status: "success"
    }
    puts JSON.generate(output)
  end

  # Ensure all spans are flushed before exit
  OpenTelemetry.tracer_provider.shutdown

rescue => e
  # Output error as JSON
  error_output = {
    result: nil,
    status: "error",
    error: e.message,
    backtrace: e.backtrace&.first(5)
  }
  puts JSON.generate(error_output)
  exit 1

end