module bridge_mul(input clock, reset, valid, input [31:0] a, b,
                  output reg [63:0] product);
  reg [31:0] captured_a, captured_b;
  reg [31:0] retired_a, retired_b, result;
  reg captured = 0;
  reg retired = 0;
  always @(posedge clock) begin
    if (reset) begin
      captured <= 0;
      retired <= 0;
    end else begin
      captured <= valid;
      retired <= captured;
      if (valid) begin
        captured_a <= a;
        captured_b <= b;
        product <= {32'd0, a} * {32'd0, b};
      end
      if (captured) begin
        retired_a <= captured_a;
        retired_b <= captured_b;
        result <= product[31:0];
      end
    end
    if (!reset) o_result: assert(!retired || result == retired_a * retired_b);
  end
endmodule
