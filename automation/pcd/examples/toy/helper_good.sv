module toy_helper;
  // h_manifold constrains the reachable state.
  always @* begin
    assert (x > 0);
  end
endmodule
